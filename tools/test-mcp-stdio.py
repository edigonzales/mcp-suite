#!/usr/bin/env python3
"""Drives every MCP tool of the interlis-mcp server over STDIO.

The probe serves two purposes:

* it is the container/CI smoke test that proves the server answers on STDIO with
  nothing but JSON-RPC on STDOUT, and
* it is the workload traced by the GraalVM native-image agent, so every tool
  argument and tool result DTO becomes part of the reachability metadata.

Usage: mcp_probe.py <command> [args...]
"""
import json
import queue
import subprocess
import sys
import threading
import time

MODEL = (
    "INTERLIS 2.4;\n"
    "\n"
    'MODEL ProbeModel (de) AT "https://example.org/probe" VERSION "2026-01-01" =\n'
    "  TOPIC Data =\n"
    "    CLASS A =\n"
    "      name : MANDATORY TEXT*20;\n"
    "    END A;\n"
    "    CLASS B =\n"
    "      count : MANDATORY 0 .. 100;\n"
    "      label : TEXT*30;\n"
    "    END B;\n"
    "    ASSOCIATION Link =\n"
    "      fromB -- {0..*} B;\n"
    "      toA -- {0..1} A;\n"
    "    END Link;\n"
    "  END Data;\n"
    "END ProbeModel.\n"
)

# A MANDATORY constraint belongs to the class that declares the referenced
# attributes, so the constraint sits inside CLASS A.
MODEL_WITH_CONSTRAINT = (
    "INTERLIS 2.4;\n"
    "\n"
    'MODEL ConstraintModel (de) AT "https://example.org/cm" VERSION "2026-01-01" =\n'
    "  TOPIC Data =\n"
    "    CLASS A =\n"
    "      name : MANDATORY TEXT*20;\n"
    "      count : MANDATORY 0 .. 100;\n"
    "      MANDATORY CONSTRAINT Positiv: count > 0;\n"
    "    END A;\n"
    "  END Data;\n"
    "END ConstraintModel.\n"
)

RENAMED_MODEL = MODEL.replace("CLASS A =", "CLASS ARenamed =")

# Associations make the scalar interaction analysis report coverage gaps, which
# is the only path that serializes ConstraintInteractionAnalysis.Gap.
MODEL_WITH_ASSOCIATION = (
    "INTERLIS 2.4;\n"
    "\n"
    'MODEL LinkedModel (de) AT "https://example.org/linked" VERSION "2026-01-01" =\n'
    "  TOPIC Data =\n"
    "    CLASS A =\n"
    "      name : MANDATORY TEXT*20;\n"
    "    END A;\n"
    "    CLASS B =\n"
    "      count : MANDATORY 0 .. 100;\n"
    "    END B;\n"
    "    MANDATORY CONSTRAINT Positiv: count > 0;\n"
    "    ASSOCIATION Link =\n"
    "      fromB -- {0..*} B;\n"
    "      toA -- {0..1} A;\n"
    "    END Link;\n"
    "  END Data;\n"
    "END LinkedModel.\n"
)

CALLS = [
    # --- model review / analysis -------------------------------------------------
    ("validateIliModel", {"modelText": MODEL}, ["valid"]),
    ("analyzeIliModel", {"modelText": MODEL, "modelPurpose": "PUBLICATION",
                         "contextFqn": "ProbeModel.Data"}, ["classes"]),
    ("reviewIliModel", {"modelText": MODEL, "modelPurpose": "PUBLICATION",
                        "ruleProfile": "SO"}, ["evidence"]),
    ("reviewIliModel", {"modelText": MODEL_WITH_ASSOCIATION, "modelPurpose": "PUBLICATION",
                        "ruleProfile": "SO"}, ["constraintInteractions"]),
    ("reviewIliChange", {"beforeModelText": MODEL, "afterModelText": RENAMED_MODEL,
                         "modelPurpose": "PUBLICATION", "ruleProfile": "CORE"}, ["evidence"]),
    ("checkModelingRules", {"modelText": MODEL, "modelPurpose": "CAPTURE",
                            "ruleIds": ["MDE-010"], "profile": "SO"}, ["SO"]),
    ("listModelingRules", {"profile": "CORE"}, ["CORE"]),
    ("formatIliModel", {"modelText": MODEL}, ["content"]),
    # --- authoring ---------------------------------------------------------------
    ("authorIliModel", {"spec": {"name": "AuthoredModel", "language": "de",
                                 "uri": "https://example.org/authored",
                                 "version": "2026-01-01", "iliVersion": "2.4",
                                 "metaAttributes": [{"name": "title", "value": "Authored"}]},
                        "modelPurpose": "CAPTURE", "ruleProfile": "CORE"},
     ["content"]),
    ("applyIliModelChanges", {
        "modelText": MODEL,
        "request": {"changes": [{"operation": "ADD_ATTRIBUTE", "addAttribute": {
            "containerFqn": "ProbeModel.Data.A",
            "attribute": {"name": "extra", "typeSpec": {"baseType": {"kind": "TEXT", "maxLength": 10}}}}}]},
        "modelPurpose": "CAPTURE", "ruleProfile": "CORE"}, ["afterReview"]),
    ("renameModelElement", {"modelText": MODEL, "elementFqn": "ProbeModel.Data.A",
                            "expectedKind": "CLASS_OR_STRUCTURE", "newName": "ARenamed"},
     ["ARenamed"]),
    # --- constraints -------------------------------------------------------------
    ("reviewIliConstraint", {"modelText": MODEL_WITH_CONSTRAINT,
                             "constraint": "ConstraintModel.Data.A.Positiv"},
     ["Positiv"]),
    ("testIliConstraint", {"modelText": MODEL_WITH_CONSTRAINT,
                           "constraint": "ConstraintModel.Data.A.Positiv",
                           "cases": [{"name": "positive", "expectedConstraintValid": True,
                                      "expectationSource": "USER_PROVIDED",
                                      "objects": [{"classFqn": "ConstraintModel.Data.A",
                                                   "values": {"name": "x", "count": 5}}]}]},
     ["cases"]),
    ("generateIliConstraintCases", {"modelText": MODEL_WITH_CONSTRAINT,
                                    "constraint": "Positiv"}, ["reasonCode"]),
    ("authorIliMandatoryConstraint", {
        "modelText": MODEL, "contextFqn": "ProbeModel.Data",
        "spec": {"kind": "MANDATORY", "name": "CountPositive", "iliDoc": "Zaehler positiv",
                 "condition": {"kind": "COMPARE", "operator": ">", "children": [
                     {"kind": "ATTRIBUTE", "name": "count"},
                     {"kind": "NUMERIC", "value": 0}]}},
        "modelPurpose": "CAPTURE", "ruleProfile": "CORE"}, ["modelHashes"]),
    ("authorIliUniqueConstraint", {
        "modelText": MODEL, "contextFqn": "ProbeModel.Data",
        "spec": {"kind": "UNIQUE", "name": "NameEindeutig", "scope": "BASKET",
                 "keyPaths": ["name"]},
        "modelPurpose": "CAPTURE", "ruleProfile": "CORE"}, ["modelHashes"]),
    ("authorIliExistenceConstraint", {
        "modelText": MODEL, "contextFqn": "ProbeModel.Data",
        "spec": {"kind": "EXISTENCE", "name": "BrauchtA", "restrictedPath": "B",
                 "requiredIn": [{"viewableFqn": "ProbeModel.Data.Link", "attributePath": "toA"}]},
        "modelPurpose": "CAPTURE", "ruleProfile": "CORE"}, ["modelHashes"]),
    ("authorIliPlausibilityConstraint", {
        "modelText": MODEL, "contextFqn": "ProbeModel.Data",
        "spec": {"kind": "PLAUSIBILITY", "name": "MeistPositiv", "direction": "AT_LEAST",
                 "percentage": 90,
                 "condition": {"kind": "COMPARE", "operator": ">", "children": [
                     {"kind": "ATTRIBUTE", "name": "count"},
                     {"kind": "NUMERIC", "value": 0}]}},
        "modelPurpose": "CAPTURE", "ruleProfile": "CORE"}, ["modelHashes"]),
    ("authorIliSetConstraint", {
        "modelText": MODEL, "contextFqn": "ProbeModel.Data",
        "spec": {"kind": "SET", "name": "GenugObjekte", "scope": "BASKET",
                 "condition": {"kind": "OBJECT_COUNT", "operator": ">=", "threshold": 1,
                               "objects": {"kind": "ALL"}}},
        "modelPurpose": "CAPTURE", "ruleProfile": "CORE"}, ["modelHashes"]),
    ("generateIliConstraintFromDecisionTable", {
        "modelText": MODEL_WITH_CONSTRAINT,
        "context": "ConstraintModel.Data.A", "constraintName": "FromTable",
        "rows": [{"name": "positiv",
                  "conditions": [{"attribute": "count", "operator": ">", "value": "0"}],
                  "expectedConstraintValid": True}]}, ["reasonCode"]),
    ("listConstraintFunctions", {"iliVersion": "2.4"}, ["functions"]),
    ("resolveConstraintPath", {"modelText": MODEL, "context": "ProbeModel.Data.A",
                               "path": "name"}, ["name"]),
    # --- geometry ----------------------------------------------------------------
    ("listGeometryTypes", {"iliVersion": "2.4"}, ["types"]),
    # --- XTF ---------------------------------------------------------------------
    ("generateExampleXtf", {"modelText": MODEL, "maxObjectsPerClass": 1}, ["xtfText"]),
    ("validateXtf", {"modelText": MODEL, "xtfText": "<TRANSFER>"}, ["valid"]),
    # --- model corpus ------------------------------------------------------------
    ("findSimilarModels", {"query": "Probe", "modelText": MODEL,
                           "modelPurpose": "CAPTURE", "limit": 3}, []),
    # Without configured model repositories every path is unknown, so the tool
    # answers with isError. The probe only requires the documented error shape.
    ("readModelExample", {"path": "does-not-exist.ili"}, ["Unable to read model example"]),
    ("indexConfiguredModels", {}, []),
]

RESOURCES = [
    "interlis://knowledge/handbook-rules",
    "interlis://knowledge/agent-workflow",
    "interlis://knowledge/model-corpus-index",
]
PROMPTS = ["interlis-modeling-agent", "review-interlis-model", "extend-interlis-model"]


class Client:
    def __init__(self, command):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1)
        self.stdout_lines = []
        self.stderr_lines = []
        self.queue = queue.Queue()
        threading.Thread(target=self._pump, args=(self.proc.stdout, self.stdout_lines, True),
                         daemon=True).start()
        threading.Thread(target=self._pump, args=(self.proc.stderr, self.stderr_lines, False),
                         daemon=True).start()

    def _pump(self, stream, sink, feed):
        for line in stream:
            sink.append(line)
            if feed:
                self.queue.put(line)
        if feed:
            self.queue.put(None)

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def await_id(self, rid, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                line = self.queue.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                continue
            if line is None:
                return None
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                return {"__nonjson__": line}
            if obj.get("id") == rid:
                return obj


def main():
    command = sys.argv[1:]
    if not command:
        print("usage: mcp_probe.py <command> [args...]", file=sys.stderr)
        return 2

    client = Client(command)
    failures = []
    per_call_timeout = 300

    client.send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "mcp-probe", "version": "1.0"}}})
    init = client.await_id(1, 120)
    if not init or "result" not in init:
        print(f"FAIL: initialize returned {init}")
        client.proc.kill()
        return 1
    print("initialize:", init["result"].get("serverInfo"))

    client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    client.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = client.await_id(2, 120)
    advertised = [t["name"] for t in tools["result"]["tools"]]
    print(f"tools/list: {len(advertised)} tools")
    probed = {name for name, _, _ in CALLS}
    for missing in sorted(probed - set(advertised)):
        failures.append(f"tool advertised nowhere but probed: {missing}")
    for unprobed in sorted(set(advertised) - probed):
        failures.append(f"advertised tool without probe coverage: {unprobed}")
    if len(CALLS) < len(advertised):
        failures.append(f"only {len(CALLS)} probes for {len(advertised)} tools")

    next_id = 100
    for name, args, expectations in CALLS:
        next_id += 1
        client.send({"jsonrpc": "2.0", "id": next_id, "method": "tools/call",
                     "params": {"name": name, "arguments": args}})
        response = client.await_id(next_id, per_call_timeout)
        if response is None:
            failures.append(f"{name}: no response within {per_call_timeout}s")
            print(f"  {name}: NO RESPONSE")
            continue
        if "__nonjson__" in response:
            failures.append(f"{name}: non-JSON on stdout: {response['__nonjson__'][:200]}")
            print(f"  {name}: NON-JSON STDOUT")
            continue
        if "error" in response:
            failures.append(f"{name}: JSON-RPC error {response['error']}")
            print(f"  {name}: JSON-RPC ERROR {str(response['error'])[:200]}")
            continue
        result = response.get("result", {})
        blob = json.dumps(result)
        # Expectations are matched against the whole result, so a probe can also
        # describe a deliberately rejected call.
        for expectation in expectations:
            if expectation not in blob:
                failures.append(f"{name}: result misses {expectation!r}")
                print(f"  {name}: missing {expectation!r}")
                break
        else:
            kind = "isError" if result.get("isError") is True else "ok"
            print(f"  {name}: {kind} ({len(blob)} bytes)")

    for index, uri in enumerate(RESOURCES):
        next_id += 1
        client.send({"jsonrpc": "2.0", "id": next_id, "method": "resources/read",
                     "params": {"uri": uri}})
        response = client.await_id(next_id, 120)
        if not response or "result" not in response:
            failures.append(f"resources/read {uri} failed: {response}")
        else:
            print(f"  resources/read {uri}: ok")

    for index, prompt in enumerate(PROMPTS):
        next_id += 1
        client.send({"jsonrpc": "2.0", "id": next_id, "method": "prompts/get",
                     "params": {"name": prompt, "arguments": {"modelPurpose": "CAPTURE"}}})
        response = client.await_id(next_id, 120)
        if not response or "result" not in response:
            failures.append(f"prompts/get {prompt} failed: {response}")
        else:
            print(f"  prompts/get {prompt}: ok")

    # STDIN EOF has to shut the process down with exit code 0.
    client.proc.stdin.close()
    try:
        exit_code = client.proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        exit_code = None
        client.proc.kill()
    if exit_code != 0:
        failures.append(f"exit code after STDIN EOF was {exit_code}, expected 0")
    print(f"exit after STDIN EOF: {exit_code}")

    # STDOUT is the MCP transport: nothing but JSON-RPC messages may appear there.
    for line in client.stdout_lines:
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            failures.append(f"non-JSON line on STDOUT: {line[:200]}")
            continue
        if obj.get("jsonrpc") != "2.0":
            failures.append(f"STDOUT line without jsonrpc marker: {line[:200]}")

    if failures:
        print("\nSTDERR tail:")
        for line in client.stderr_lines[-15:]:
            print("  " + line.rstrip())
        print("\nFAIL")
        for failure in failures:
            print("  - " + failure)
        return 1

    print("\nPASS: every tool, resource and prompt answered over STDIO with clean STDOUT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
