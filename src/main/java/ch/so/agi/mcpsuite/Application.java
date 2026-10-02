package ch.so.agi.mcpsuite;

import ch.so.agi.mcp.InterlisMcpModuleConfiguration;
import ch.so.agi.netl.NetlMcpModuleConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import({InterlisMcpModuleConfiguration.class, NetlMcpModuleConfiguration.class})
public class Application {
    public static void main(String[] args) { SpringApplication.run(Application.class, args); }
}
