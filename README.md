# mcp-suite

INTERLIS und NETL in einer Java-21-JVM, einem Spring-Kontext und einem MCP-Server.
Die Module bleiben in ihren eigenen GitHub-Repositories und liefern weiterhin
je ein Standalone-Image. Die Suite importiert ausdrücklich
`InterlisMcpModuleConfiguration` und `NetlMcpModuleConfiguration`.
Sie bietet die Vereinigung ihrer Tools, Resources und Prompts ohne Umbenennungen
oder Bean-Überschreibungen an; ihre Serveridentität ist `mcp-suite`.

## Build und Start

Java 21 und Gradle 9.5.1. Standardmässig werden die Modul-Snapshots von
`https://jars.interlis.guru/snapshots/` konsumiert:

```sh
./gradlew check bootJar
# STDIO ist der lokale Standard:
java -jar build/libs/mcp-suite.jar
# Streamable HTTP, WebMVC, SYNC, /mcp auf Port 8080:
java -jar build/libs/mcp-suite.jar --spring.profiles.active=http
```

Für lokale Entwicklung mit benachbarten Checkouts `../interlis-mcp` und `../netl-mcp`:

```sh
./gradlew -PuseLocalModules=true check bootJar
./gradlew -PuseLocalModules=true buildImage
```

Der Schalter ist ausdrücklich erforderlich; veröffentlichte Snapshots werden sonst
nicht durch lokale Projekte ersetzt. Die Suite prüft alle aufgelösten Modul-Dependencies
gegen beide Modulmanifeste und stoppt bei Abweichungen. Die gemeinsame Versionierung
verwendet Boot 4.1.1, Spring AI 2.0.1, MCP SDK 2.0.1 und JSpecify 1.0.1.
Die MCP-JSON-Verarbeitung verwendet Jackson 3, NETLs Fach-JSON Jackson 2 aus dem Boot-BOM.
Die Suite übernimmt INTERLIS' Request-Timeout von einer Stunde; NETLs fachliche
120-Sekunden-Fristen bleiben bestehen. Native-Builds sind deaktiviert.

## Docker

Die Images `sogis/mcp-suite` und `ghcr.io/edigonzales/mcp-suite` unterstützen
`linux/amd64` und `linux/arm64`. Standardprofil im Image ist HTTP:

```sh
# Offline lesbarer NETL-Workspace, HTTP ausschliesslich auf Loopback:
docker run --rm -p 127.0.0.1:8080:8080 \
  -v "$PWD/tests/fixture:/workspace:ro" -e NETL_WORKSPACE=/workspace \
  sogis/mcp-suite:latest
# STDIO, kein TTY:
docker run --rm -i -e SPRING_PROFILES_ACTIVE=stdio \
  -v "$PWD/tests/fixture:/workspace:ro" -e NETL_WORKSPACE=/workspace \
  ghcr.io/edigonzales/mcp-suite:latest
```

Für NETL-Schemaimporte und GRETL-Jobs benötigt die Suite einen schreibbaren Workspace,
`NETL_RUNTIME_MODE=container`, `NETL_HOST_WORKSPACE` mit dem absoluten Hostpfad,
das Datenbanknetzwerk und Docker-Socket-Zugriff mit passenden Gruppenrechten.
Docker-CLI ist im Suite-Image enthalten; GRETL bleibt ein separater persistenter Dienst.
Alle JDBC-Zugriffe, einschliesslich temporärer Jobrollen, verwenden die gemeinsame
NETL-Laufzeitkonfiguration. INTERLIS-Modellpfade können weiterhin über
`INTERLIS_KNOWLEDGE_MODEL_PATHS` gesetzt werden.

Ein ausführbares Compose-Beispiel und das unabhängige synthetische Lab liegen im
[NETL-Repository](https://github.com/edigonzales/netl-mcp/blob/main/tests/compose/README.md).
Dort `MCP_IMAGE=sogis/mcp-suite:latest` setzen. Server-Workspace und Hostpfad werden getrennt
behandelt; Runner-Mount, Container, Image, Compose-Projekt, Sperren und Recovery bleiben geprüft.

## Prüfungen und Veröffentlichung

```sh
./gradlew -PuseLocalModules=true check bootJar buildImage
python3 tools/check-image.py --kind suite --image sogis/mcp-suite:latest \
  --workspace tests/fixture --catalog build/suite-catalog.json --jar build/libs/mcp-suite.jar
```

CI verwendet ausschliesslich veröffentlichte Snapshots. Nach Fach-/Kompositionstests
wird das kanonische JAR einmal gebaut; beide Image-Architekturen erhalten dieselben Bytes.
HTTP-/STDIO-Prüfungen testen Initialisierung, Toolkatalog, Resources, Prompts,
repräsentative Aufrufe, parallele Antworten und geordnetes Beenden. Der vollständige
Suite-Katalog wird mit beiden veröffentlichten Einzelservern verglichen.
Ein weiterer Test betreibt die Suite am synthetischen NETL-Lab und prüft echte
Schema- und Jobabläufe aus dem Container.

Main-Pushes und manuelle Main-Läufe veröffentlichen nach erfolgreichen Prüfungen auf
Docker Hub und GHCR; PRs veröffentlichen nichts. Die Tagbasis ist `0.0`, ergänzt um
CI-Laufnummer und Versuch; `latest` wird nach erfolgreichen Architekturtests und
Manifestprüfungen aktualisiert. Zuerst Module und Einzelimages veröffentlichen,
anschliessend die Suite. Neue Suite-Builds erfolgen durch Änderungen in diesem Repo
oder `workflow_dispatch`; automatische repoübergreifende Trigger sind nicht eingerichtet.
Details: [Module und Veröffentlichung](docs/MODULES.md).
