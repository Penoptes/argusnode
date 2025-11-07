# argusnode
Monitoring Stack for 3CX

The ArgusNode Multi-Tenant 3CX Monitoring Stack
This solution is an advanced, open-source monitoring stack designed from the ground up to support a large 3CX reseller base. It solves the critical challenges of data isolation, security, and deep VoIP quality analysis in a single, repeatable, and scalable deployment model.

1. Zero-Trust, Per-Client Data Isolation
   
The most critical feature for a reseller is security and regulatory compliance. Our stack achieves this through deep containerization on your central Huawei Cloud ECS host:

    Isolated Log Servers: For every 3CX client you onboard, a dedicated, isolated Ubuntu container is deployed. This container houses the client’s entire logging infrastructure.

    The Isolation Guarantee: This architecture ensures that Client A's sensitive call logs, performance metrics, and configuration data are physically and logically separated from Client B's data. This eliminates the risk of cross-client data leakage and simplifies compliance audits.

    Templated Deployment: Deploying a new client is fast and automated. We use a templated configuration that spins up a new, pre-configured log server container with a single command, making client onboarding fast and efficient.

3. Deep VoIP and Call Quality Forensics 🎙️

Standard monitoring only tells you if the server is up. Our stack provides the insights needed to solve elusive call quality issues:

    RTP Stream Analysis: The lightweight monitoring Probe installed on the client's 3CX Debian server doesn't just check CPU load; it actively monitors and logs real-time data from the VoIP infrastructure, specifically capturing RTP (Real-time Transport Protocol) streams.

    MOS Rating Capture: Crucially, the probe gathers the Mean Opinion Score (MOS) rating for calls. This is the definitive metric for human-perceived call quality. By logging MOS, you move from reacting to "bad call quality" complaints to proactively identifying the exact time, handset, and stream where a score dropped (e.g., below 4.0).

3. Secure, Optimized Data Transport 📡

Performance and security are balanced to ensure minimal impact on the client's live 3CX server:

    Compressed Transfer: All log data and metrics are processed and compressed by the local agent before leaving the client server, ensuring minimal bandwidth consumption and fast transport times.

    End-to-End Encryption: Data is transmitted over an encrypted channel (utilizing Zabbix Agent encryption or a secure logging protocol) to the client’s dedicated container, guaranteeing secure transport and protecting sensitive customer information from interception.

4. Scalable Centralized Management ⚙️

The entire system is centrally managed via the powerful Zabbix platform, providing a single pane of glass for your entire customer base:

    Dynamic Port Management: The system handles the complex networking challenge of routing hundreds of client connections to the single public IP address of the monitoring host. Each client container is assigned a unique TCP/UDP port that is automatically managed and tracked, ensuring that connections are always correctly forwarded to the right isolated client instance.

    Open-Source Foundation: The entire stack—built on Zabbix, Docker, and Ubuntu—is 100% open-source, eliminating licensing costs and offering maximum flexibility for customization and long-term support.

Monitoring Stack Design:

Isolation Strategy & Cost: The design uses a per-client container for log isolation. At what scale (e.g., number of clients) does the cost and overhead of managing hundreds of individual containers exceed the benefit of a single, multi-tenant Zabbix/logging instance with RBAC and robust tagging?

RTP Data Flood Control: 
The stack captures high-volume VoIP/RTP stream and MOS data. Is the monitoring probe configured to filter this data (e.g., only log streams when MOS drops below 4.0) to prevent a storage and bandwidth flood, or is all stream data being captured and transmitted?

Unique Port Management (IaC): 
Since every client container needs a unique public port on the main host, what specific Infrastructure-as-Code (IaC) tool or automation layer is used to reliably map and track these hundreds of NAT entries without manual configuration or port conflicts?

Log Data Security: 
Encryption is used in transit (agent to container), but how are the logs secured at rest inside the client containers? What is the defined process for log retention, rotation, and recovery in the event of a host-level failure?

Agent Security Audit: 
Given that the monitoring probe runs on the critical 3CX server, what security audit or privilege limiting is in place to ensure that a compromised Zabbix Agent (via a malicious UserParameter or code execution) cannot pivot and access other sensitive parts of the 3CX server?
