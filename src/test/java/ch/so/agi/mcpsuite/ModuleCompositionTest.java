package ch.so.agi.mcpsuite;

import io.modelcontextprotocol.server.McpSyncServer;
import io.modelcontextprotocol.server.McpServerFeatures.SyncToolSpecification;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import java.util.List;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties={"spring.profiles.active=http", "spring.main.allow-bean-definition-overriding=false"})
class ModuleCompositionTest {
    @Autowired ApplicationContext context;
    @Autowired @Qualifier("toolSpecs") List<SyncToolSpecification> tools;
    @Autowired @Qualifier("configurationTools") List<SyncToolSpecification> configurationTools;
    @Test void oneServerCombinesCapabilitiesWithoutOverrides() {
        assertThat(context.getBeansOfType(McpSyncServer.class)).hasSize(1);
        var names=tools.stream().map(t -> t.tool().name()).toList();
        assertThat(names).doesNotHaveDuplicates();
        assertThat(names).contains("reviewIliModel", "authorIliModel", "schema_create", "job_test");
        assertThat(context.getEnvironment().getProperty("spring.ai.mcp.server.name")).isEqualTo("mcp-suite");
        assertThat(context.getEnvironment().getProperty("spring.ai.mcp.server.stdio")).isEqualTo("false");
    }
    @Test void netlNumericSchemaSurvivesInterlisNormalization() {
        var tool=configurationTools.stream().filter(t -> t.tool().name().equals("config_save")).findFirst().orElseThrow().tool();
        @SuppressWarnings("unchecked") var props=(java.util.Map<String,Object>) tool.inputSchema().get("properties");
        @SuppressWarnings("unchecked") var manifest=(java.util.Map<String,Object>) props.get("manifest");
        @SuppressWarnings("unchecked") var fields=(java.util.Map<String,Object>) manifest.get("properties");
        @SuppressWarnings("unchecked") var version=(java.util.Map<String,Object>) fields.get("formatVersion");
        assertThat(version).containsEntry("type", "integer");
    }
}
