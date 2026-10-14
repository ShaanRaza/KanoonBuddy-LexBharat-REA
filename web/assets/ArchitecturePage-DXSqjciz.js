import{j as e,P as r,M as a}from"./index-Ac-JwDP4.js";import{A as s,r as i,s as n,t as o,K as c,D as l,u as d,N as u}from"./icons-CYH3BR3F.js";import{L as t}from"./react-vendor-9b-Fppbo.js";import"./modulepreload-polyfill-B5Qt9EMX.js";import"./mermaid-Iu9CgLAS.js";import"./motion-DRT_oqBn.js";const p=`
# LexBharat AI - System Architecture & Security

## Overview

LexBharat AI is a comprehensive legal research and document management platform built with enterprise-grade security. This document provides a high-level overview of the system architecture and the multiple layers of protection that safeguard user data and system integrity.

---

## High-Level Architecture

\`\`\`mermaid
flowchart TB
    subgraph Clients["🌐 Client Layer"]
        Browser["👤 Web Browser<br/>lexbharat.ai"]
        Mobile["📱 Mobile App<br/>iOS / Android"]
        WordAddin["📄 Word Add-in<br/>Office Integration"]
    end

    subgraph DNS["📡 DNS Layer"]
        Route53["🌍 Route 53<br/>lexbharat.ai<br/>DNS Resolution"]
    end

    subgraph Edge["🛡️ Edge Security Layer"]
        WAF["🛡️ AWS WAF<br/>━━━━━━━━━━━━<br/>• Rate Limiting: 2000/5min<br/>• SQL Injection Rules<br/>• XSS Protection<br/>• Known Bad Inputs"]
    end

    subgraph LoadBalancer["⚖️ Load Balancer Layer"]
        ALB["⚖️ Application Load Balancer<br/>━━━━━━━━━━━━━━━━━━━━━<br/>HTTPS Only (Port 443)<br/>TLS 1.3 Termination<br/>Health Checks"]

        subgraph Listeners["Listener Rules"]
            L443["Port 443 (HTTPS)<br/>Default: → App"]
        end
    end

    subgraph Auth["🔐 Authentication Layer"]
        Google["🔑 Google OAuth 2.0<br/>━━━━━━━━━━━━<br/>Identity Provider<br/>SSO Integration"]
    end

    subgraph Compute["🐳 ECS Compute Layer"]
        ECS["🐳 ECS Cluster<br/>EC2 Launch Type"]

        subgraph Container["📦 ECS Task / Container"]
            App["🚀 Node.js Backend<br/>━━━━━━━━━━━━<br/>Port 3001<br/>Express API<br/>React Frontend"]

            subgraph BrowserStack["🖼️ Headless Browser Stack"]
                Xvfb["🖼️ Xvfb<br/>Virtual Display :99"]
                Chromium["🌍 Chromium<br/>Headless Browser"]
            end
        end
    end

    subgraph Data["💾 Data Layer"]
        subgraph DataStores["Persistent Storage"]
            RDS["🗄️ PostgreSQL RDS<br/>━━━━━━━━━━━━<br/>Port 5432<br/>pgvector Extension<br/>Case Embeddings"]
            S3["📁 S3 Bucket<br/>━━━━━━━━━━━━<br/>Document Storage<br/>Server-side Encryption"]
        end

        subgraph Secrets["Credential Management"]
            SecretsMgr["🔒 Secrets Manager<br/>━━━━━━━━━━━━<br/>• API Keys<br/>• DB Credentials"]
        end
    end

    subgraph External["🌐 External Services"]
        OpenAI["🤖 OpenAI API<br/>GPT-4 / Embeddings"]
        Kanoon["⚖️ Indian Kanoon<br/>Case Database"]
        Anthropic["🧠 Anthropic API<br/>Claude AI"]
    end

    %% Flow connections
    Browser --> Route53
    Mobile --> Route53
    WordAddin --> Route53
    Route53 -->|"DNS Lookup"| WAF
    WAF -->|"Filtered Traffic"| ALB
    ALB --> L443
    L443 -->|"Port 3001"| App
    App -->|"ID token verify"| Google
    Xvfb --> Chromium
    App -->|"Port 5432"| RDS
    App --> S3
    App --> SecretsMgr
    App --> OpenAI
    App --> Kanoon
    App --> Anthropic
\`\`\`

---

## Port Reference

| Service | Port | Protocol | Access |
|---------|------|----------|--------|
| **HTTPS (Public)** | 443 | TCP | Internet → ALB |
| **Node.js App** | 3001 | HTTP | ALB → ECS Task |
| **PostgreSQL** | 5432 | TCP | ECS Task → RDS (Private) |
| **Xvfb Display** | :99 | X11 | Container internal |

---

## Security Architecture - Defense in Depth

Our security model implements multiple layers of protection, ensuring that even if one layer is compromised, others remain intact.

\`\`\`mermaid
flowchart LR
    subgraph Layer1["Layer 1: Network Edge"]
        WAF["AWS WAF"]
        DDoS["DDoS Protection"]
        RateLimit["Rate Limiting<br/>2000 req/5min"]
    end

    subgraph Layer2["Layer 2: Transport"]
        TLS["TLS 1.3<br/>Encryption"]
        HTTPS["HTTPS Only<br/>HTTP Redirect"]
    end

    subgraph Layer3["Layer 3: Authentication"]
        OAuth["Google OAuth 2.0"]
        JWT["JWT Tokens"]
    end

    subgraph Layer4["Layer 4: Authorization"]
        RBAC["Role-Based<br/>Access Control"]
        SessionMgmt["Session<br/>Management"]
    end

    subgraph Layer5["Layer 5: Application"]
        InputVal["Input Validation"]
        SQLParam["Parameterized<br/>Queries"]
        XSS["XSS Protection"]
    end

    subgraph Layer6["Layer 6: Data"]
        Encryption["Encryption<br/>at Rest"]
        SecretsMgr["Secrets<br/>Manager"]
        VPC["Private<br/>Subnets"]
    end

    Layer1 --> Layer2 --> Layer3 --> Layer4 --> Layer5 --> Layer6
\`\`\`

---

## Client Request Flow - How Users Are Protected

When a user interacts with LexBharat AI, their request passes through multiple security checkpoints:

\`\`\`mermaid
sequenceDiagram
    autonumber
    participant User as 👤 User
    participant WAF as 🛡️ AWS WAF
    participant ALB as ⚖️ Load Balancer
    participant App as 📦 Application
    participant DB as 🗄️ Database

    User->>WAF: HTTPS Request

    Note over WAF: Check #1: WAF Rules
    WAF->>WAF: Rate limit check
    WAF->>WAF: SQL injection scan
    WAF->>WAF: XSS pattern check
    WAF->>WAF: Known bad inputs

    alt Request Blocked
        WAF-->>User: 403 Forbidden
    else Request Allowed
        WAF->>ALB: Forward Request
    end

    Note over ALB: Check #2: TLS Termination
    ALB->>ALB: Verify TLS certificate
    ALB->>ALB: Check host header

    Note over App: Check #3: Authentication + Authorization
    ALB->>App: Forward request
    App->>App: Verify JWT (issued after Google Sign-In)
    App->>App: Check user permissions

    Note over DB: Check #4: Data Access
    App->>DB: Parameterized query
    DB->>DB: Row-level security
    DB-->>App: Filtered results

    App-->>User: Secure response
\`\`\`

---

## Data Protection Architecture

\`\`\`mermaid
flowchart LR
    subgraph Ingress["Data Ingress"]
        Upload["📤 Document Upload"]
        Input["⌨️ User Input"]
        API["🔗 API Data"]
    end

    subgraph Processing["Processing"]
        Validate["✅ Validation<br/>Type & Size Check"]
        Sanitize["🧹 Sanitization<br/>XSS Prevention"]
        Encrypt["🔐 Encryption<br/>AES-256"]
    end

    subgraph Storage["Secure Storage"]
        S3Enc["📁 S3<br/>Server-side Encryption"]
        RDSEnc["🗄️ RDS<br/>TLS in Transit"]
        SecMgr["🔒 Secrets Manager<br/>Encrypted at Rest"]
    end

    subgraph Access["Access Control"]
        IAM["👤 IAM Roles<br/>Least Privilege"]
        VPCFlow["🌐 VPC<br/>Private Subnets"]
        SG["🛡️ Security Groups<br/>Strict Rules"]
    end

    Upload --> Validate
    Input --> Validate
    API --> Validate
    Validate --> Sanitize
    Sanitize --> Encrypt
    Encrypt --> S3Enc
    Encrypt --> RDSEnc
    Encrypt --> SecMgr
    S3Enc --> IAM
    RDSEnc --> VPCFlow
    SecMgr --> SG
\`\`\`

---

## Network Security - VPC Architecture (In-Depth)

### VPC Overview

The entire LexBharat infrastructure runs inside a dedicated Virtual Private Cloud (VPC) with carefully segmented subnets and strict security group rules.

\`\`\`mermaid
flowchart TB
    subgraph Internet["🌐 Internet"]
        Users["👥 Users<br/>Worldwide"]
        ExtAPI["🔗 External APIs<br/>OpenAI, Indian Kanoon"]
    end

    subgraph IGW["Internet Gateway"]
        Gateway["🚪 IGW<br/>lawcentral-igw"]
    end

    subgraph VPC["☁️ VPC: lawcentral-vpc (10.1.0.0/16)"]

        subgraph AZ1["Availability Zone 1 (us-east-2a)"]
            subgraph Pub1["Public Subnet 1<br/>10.1.1.0/24"]
                ALB1["⚖️ ALB Node"]
                NAT1["🌐 NAT Gateway 1<br/>Elastic IP"]
            end

            subgraph Priv1["Private Subnet 1<br/>10.1.10.0/24"]
                ECS1["📦 ECS Task<br/>Instance 1"]
            end
        end

        subgraph AZ2["Availability Zone 2 (us-east-2b)"]
            subgraph Pub2["Public Subnet 2<br/>10.1.2.0/24"]
                ALB2["⚖️ ALB Node"]
                NAT2["🌐 NAT Gateway 2<br/>Elastic IP"]
            end

            subgraph Priv2["Private Subnet 2<br/>10.1.20.0/24"]
                RDS1["🗄️ RDS Primary"]
            end
        end

        subgraph AZ3["Availability Zone 3 (us-east-2c)"]
            subgraph Pub3["Public Subnet 3<br/>10.1.3.0/24"]
                ALB3["⚖️ ALB Node"]
            end

            subgraph Priv3["Private Subnet 3<br/>10.1.30.0/24"]
                RDS2["🗄️ RDS Standby"]
            end
        end
    end

    %% Ingress flow
    Users -->|"HTTPS:443"| Gateway
    Gateway --> ALB1
    Gateway --> ALB2
    Gateway --> ALB3
    ALB1 -->|"Port 3001"| ECS1
    ALB2 -->|"Port 3001"| ECS1

    %% Private connections
    ECS1 -->|"Port 5432"| RDS1
    RDS1 <-->|"Replication"| RDS2

    %% Egress flow (NAT)
    ECS1 -->|"Outbound"| NAT1
    NAT1 -->|"Internet"| Gateway
    Gateway --> ExtAPI
\`\`\`

### Subnet Design

| Subnet Type | CIDR Block | Resources | Internet Access |
|-------------|------------|-----------|-----------------|
| **Public Subnet 1** | 10.1.1.0/24 | ALB, NAT Gateway | Direct (IGW) |
| **Public Subnet 2** | 10.1.2.0/24 | ALB, NAT Gateway | Direct (IGW) |
| **Public Subnet 3** | 10.1.3.0/24 | ALB | Direct (IGW) |
| **Private Subnet 1** | 10.1.10.0/24 | ECS Tasks | Outbound only (NAT) |
| **Private Subnet 2** | 10.1.20.0/24 | RDS Primary | None |
| **Private Subnet 3** | 10.1.30.0/24 | RDS Standby | None |

### Route Tables

\`\`\`mermaid
flowchart LR
    subgraph PublicRT["📋 Public Route Table"]
        PR1["0.0.0.0/0 → IGW"]
        PR2["10.1.0.0/16 → local"]
    end

    subgraph PrivateRT["📋 Private Route Table"]
        PvR1["0.0.0.0/0 → NAT Gateway"]
        PvR2["10.1.0.0/16 → local"]
    end

    subgraph DBRT["📋 Database Route Table"]
        DBR1["10.1.0.0/16 → local"]
        DBR2["No internet route"]
    end

    PublicRT -->|"Attached to"| PubSub["Public Subnets<br/>10.1.1-3.0/24"]
    PrivateRT -->|"Attached to"| PrivSub["Private Subnet<br/>10.1.10.0/24"]
    DBRT -->|"Attached to"| DBSub["DB Subnets<br/>10.1.20-30.0/24"]
\`\`\`

### NAT Gateway - Outbound Traffic Flow

NAT Gateway enables ECS tasks in private subnets to access external APIs (OpenAI, Indian Kanoon, etc.) without exposing them to inbound internet traffic.

\`\`\`mermaid
sequenceDiagram
    autonumber
    participant ECS as 📦 ECS Task<br/>(Private: 10.1.10.x)
    participant NAT as 🌐 NAT Gateway<br/>(Elastic IP)
    participant IGW as 🚪 Internet Gateway
    participant API as 🤖 OpenAI API

    Note over ECS: Need to call OpenAI API

    ECS->>NAT: Request to api.openai.com<br/>Source: 10.1.10.x
    Note over NAT: Source NAT (SNAT)<br/>Replace private IP with Elastic IP
    NAT->>IGW: Forward request<br/>Source: Elastic IP
    IGW->>API: HTTPS request

    API->>IGW: Response
    IGW->>NAT: Forward response<br/>Dest: Elastic IP
    Note over NAT: Reverse NAT<br/>Replace Elastic IP with 10.1.10.x
    NAT->>ECS: Response delivered<br/>Dest: 10.1.10.x

    Note over ECS: ✅ API call successful<br/>Private IP never exposed
\`\`\`

### Security Groups - Detailed Rules

\`\`\`mermaid
flowchart TB
    subgraph SG_ALB["🛡️ ALB Security Group"]
        direction TB
        ALB_In["📥 INBOUND<br/>━━━━━━━━━━<br/>443 TCP from 0.0.0.0/0<br/>80 TCP from 0.0.0.0/0<br/>(redirect to 443)"]
        ALB_Out["📤 OUTBOUND<br/>━━━━━━━━━━<br/>3001 TCP to Task SG"]
    end

    subgraph SG_Task["🛡️ ECS Task Security Group"]
        direction TB
        Task_In["📥 INBOUND<br/>━━━━━━━━━━<br/>3001 TCP from ALB SG"]
        Task_Out["📤 OUTBOUND<br/>━━━━━━━━━━<br/>443 TCP to 0.0.0.0/0<br/>(via NAT)<br/>5432 TCP to DB SG"]
    end

    subgraph SG_DB["🛡️ RDS Security Group"]
        direction TB
        DB_In["📥 INBOUND<br/>━━━━━━━━━━<br/>5432 TCP from Task SG<br/>ONLY"]
        DB_Out["📤 OUTBOUND<br/>━━━━━━━━━━<br/>None (stateful replies)"]
    end

    Internet["🌐 Internet"] -->|"443"| SG_ALB
    SG_ALB -->|"3001"| SG_Task
    SG_Task -->|"5432"| SG_DB
    SG_Task -->|"443 via NAT"| External["🔗 External APIs"]
\`\`\`

### Security Group Rules Table

| Security Group | Direction | Port | Protocol | Source/Destination | Purpose |
|----------------|-----------|------|----------|-------------------|---------|
| **ALB SG** | Inbound | 443 | TCP | 0.0.0.0/0 | HTTPS from internet |
| **ALB SG** | Inbound | 80 | TCP | 0.0.0.0/0 | HTTP (redirects to 443) |
| **ALB SG** | Outbound | 3001 | TCP | Task SG | Forward to app |
| **Task SG** | Inbound | 3001 | TCP | ALB SG | App traffic |
| **Task SG** | Outbound | 443 | TCP | 0.0.0.0/0 | External APIs (via NAT) |
| **Task SG** | Outbound | 5432 | TCP | DB SG | Database access |
| **DB SG** | Inbound | 5432 | TCP | Task SG | PostgreSQL connections |
| **DB SG** | Outbound | - | - | - | None (isolated) |

### Network ACLs (NACLs)

Network ACLs provide an additional stateless firewall at the subnet level:

\`\`\`mermaid
flowchart LR
    subgraph PublicNACL["📋 Public Subnet NACL"]
        PN1["✅ Allow 443 inbound"]
        PN2["✅ Allow 80 inbound"]
        PN3["✅ Allow ephemeral outbound"]
        PN4["❌ Deny all else"]
    end

    subgraph PrivateNACL["📋 Private Subnet NACL"]
        PvN1["✅ Allow from VPC CIDR"]
        PvN2["✅ Allow ephemeral inbound"]
        PvN3["✅ Allow 443 outbound"]
        PvN4["❌ Deny direct internet"]
    end

    subgraph DBNACL["📋 Database Subnet NACL"]
        DBN1["✅ Allow 5432 from 10.1.10.0/24"]
        DBN2["❌ Deny all internet"]
        DBN3["❌ Deny all other subnets"]
    end
\`\`\`

---

## Authentication Flow - Google Sign-In

\`\`\`mermaid
sequenceDiagram
    participant User as 👤 User
    participant App as 📱 LexBharat
    participant API as 📦 Backend API
    participant Google as 🔑 Google

    User->>App: Access protected resource
    App-->>User: Show sign-in

    User->>Google: Sign in with Google
    Google->>Google: Verify identity
    Google-->>App: ID token

    App->>API: POST /api/auth/google (ID token)
    API->>Google: Verify token signature + audience
    API->>API: Create/update user, issue JWT (7d)
    API-->>App: JWT

    App->>API: Requests with Authorization: Bearer JWT
    API->>API: Verify JWT, load roles
    API-->>User: Serve protected content
\`\`\`

---

## Threat Protection Matrix

| Threat | Protection Layer | Mechanism |
|--------|------------------|-----------|
| **DDoS Attack** | WAF | Rate limiting (2000 req/5min per IP) |
| **SQL Injection** | WAF + App | AWS Managed Rules + Parameterized queries |
| **XSS Attack** | WAF + App | Pattern blocking + Input sanitization |
| **Brute Force** | App | Per-IP rate limits on login/OTP + reCAPTCHA |
| **CSRF** | App | JWT tokens in headers (not cookies) |
| **Man-in-the-Middle** | ALB | TLS 1.3 encryption |
| **Unauthorized Access** | App | Google Sign-In + JWT verification on every request |
| **Data Breach** | Multiple | Encryption, VPC isolation, Secrets Manager |
| **Credential Theft** | Secrets Manager | No hardcoded secrets, rotation support |
| **Session Hijacking** | App | Signed JWT in Authorization header, HTTPS only |

---

## Compliance & Best Practices

### Security Standards Implemented

- **OWASP Top 10** - Protection against common web vulnerabilities
- **AWS Well-Architected** - Security pillar best practices
- **Defense in Depth** - Multiple security layers
- **Principle of Least Privilege** - Minimal IAM permissions
- **Zero Trust** - Verify every request

### Monitoring & Audit

\`\`\`mermaid
flowchart LR
    subgraph Sources["Log Sources"]
        WAFLogs["WAF Logs"]
        ALBLogs["ALB Access Logs"]
        AppLogs["Application Logs"]
        DBLogs["RDS Logs"]
    end

    subgraph Collection["Collection"]
        CW["☁️ CloudWatch<br/>Log Groups"]
    end

    subgraph Analysis["Analysis"]
        Metrics["📊 Metrics"]
        Alarms["🚨 Alarms"]
        Insights["🔍 Insights"]
    end

    WAFLogs --> CW
    ALBLogs --> CW
    AppLogs --> CW
    DBLogs --> CW

    CW --> Metrics
    CW --> Alarms
    CW --> Insights
\`\`\`

---

## Summary

LexBharat AI implements a comprehensive security architecture that protects user data at every level:

1. **Edge Protection** - WAF blocks malicious traffic before it reaches the application
2. **Encrypted Transport** - All data in transit is encrypted with TLS 1.3
3. **Strong Authentication** - Google Sign-In with server-side ID-token verification ensures verified identities
4. **Application Security** - Input validation, parameterized queries, and XSS protection
5. **Data Protection** - Encryption at rest, Secrets Manager for credentials
6. **Network Isolation** - Private subnets, security groups, and VPC architecture

This multi-layered approach ensures that even if one security control fails, others remain in place to protect the system and its users.
`,x=()=>e.jsx(r,{children:e.jsxs("div",{className:"min-h-screen bg-gradient-to-b from-gray-50 to-white",children:[e.jsx("div",{className:"bg-white border-b border-gray-200",children:e.jsxs("div",{className:"max-w-6xl mx-auto px-4 py-6",children:[e.jsxs(t,{to:"/admin/blog",className:"inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4 transition-colors",children:[e.jsx(s,{className:"w-4 h-4"}),e.jsx("span",{children:"Back to Admin"})]}),e.jsxs("div",{className:"flex items-center gap-4",children:[e.jsx("div",{className:"p-3 bg-gradient-to-br from-amber-100 to-amber-50 rounded-xl",children:e.jsx(i,{className:"w-8 h-8 text-amber-700"})}),e.jsxs("div",{children:[e.jsx("h1",{className:"text-2xl font-bold text-gray-900 tracking-tight",children:"System Architecture & Security"}),e.jsx("p",{className:"text-gray-600 mt-1",children:"Comprehensive overview of LexBharat AI infrastructure"})]})]})]})}),e.jsxs("div",{className:"max-w-6xl mx-auto px-4 py-8",children:[e.jsxs("div",{className:"grid grid-cols-2 md:grid-cols-4 gap-4 mb-8",children:[e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-green-100 rounded-lg",children:e.jsx(n,{className:"w-5 h-5 text-green-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"WAF Protected"}),e.jsx("div",{className:"text-xs text-gray-500",children:"DDoS & Attack Prevention"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-blue-100 rounded-lg",children:e.jsx(o,{className:"w-5 h-5 text-blue-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"TLS 1.3"}),e.jsx("div",{className:"text-xs text-gray-500",children:"Encrypted Transport"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-purple-100 rounded-lg",children:e.jsx(c,{className:"w-5 h-5 text-purple-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"OAuth 2.0"}),e.jsx("div",{className:"text-xs text-gray-500",children:"Google Sign-In"})]})]}),e.jsxs("div",{className:"bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-3",children:[e.jsx("div",{className:"p-2 bg-amber-100 rounded-lg",children:e.jsx(l,{className:"w-5 h-5 text-amber-700"})}),e.jsxs("div",{children:[e.jsx("div",{className:"text-sm font-medium text-gray-900",children:"Secrets Manager"}),e.jsx("div",{className:"text-xs text-gray-500",children:"Secure Credentials"})]})]})]}),e.jsxs("div",{className:"bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-6 mb-8 text-white",children:[e.jsxs("div",{className:"flex items-center gap-2 mb-4",children:[e.jsx(d,{className:"w-5 h-5 text-amber-400"}),e.jsx("h2",{className:"text-lg font-semibold",children:"Security Layers"})]}),e.jsxs("div",{className:"grid grid-cols-2 md:grid-cols-6 gap-4",children:[e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-amber-400",children:"6"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Defense Layers"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-green-400",children:"3"}),e.jsx("div",{className:"text-xs text-gray-400",children:"WAF Rule Sets"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-blue-400",children:"2000"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Rate Limit/5min"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-purple-400",children:"TLS 1.3"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Encryption"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-pink-400",children:"VPC"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Network Isolation"})]}),e.jsxs("div",{className:"text-center",children:[e.jsx("div",{className:"text-2xl font-bold text-cyan-400",children:"IAM"}),e.jsx("div",{className:"text-xs text-gray-400",children:"Least Privilege"})]})]})]})]}),e.jsx("div",{className:"max-w-6xl mx-auto px-4 pb-16",children:e.jsx("div",{className:"bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden",children:e.jsx("div",{className:"p-8 md:p-12",children:e.jsx(a,{content:p})})})}),e.jsx("div",{className:"border-t border-gray-200 bg-gray-50",children:e.jsx("div",{className:"max-w-6xl mx-auto px-4 py-8",children:e.jsxs("div",{className:"flex items-center justify-between",children:[e.jsxs("div",{className:"flex items-center gap-2 text-gray-600",children:[e.jsx(u,{className:"w-4 h-4"}),e.jsx("span",{className:"text-sm",children:"Last updated: February 2026"})]}),e.jsxs("div",{className:"flex items-center gap-4",children:[e.jsx(t,{to:"/admin/blog",className:"text-sm text-gray-600 hover:text-gray-900 transition-colors",children:"Admin Blog"}),e.jsx(t,{to:"/docs",className:"text-sm text-gray-600 hover:text-gray-900 transition-colors",children:"Documentation"})]})]})})})]})});export{x as default};
