# HTTPS/TLS Setup Guide for EduSense

This document describes how to configure HTTPS/TLS for the EduSense platform in production environments.

## Overview

EduSense runs as a FastAPI backend (port 8000) with a React frontend (port 5173). For production, you should terminate TLS at a reverse proxy (nginx, Caddy, or cloud load balancer) rather than in the application itself.

## Option 1: nginx with Let's Encrypt (Recommended for VM/EC2)

### Prerequisites
- Domain name pointing to your server
- Ubuntu/Debian or similar Linux server
- Root/sudo access

### Installation

```bash
# Install nginx and certbot
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

### nginx Configuration

Create `/etc/nginx/sites-available/edusense`:

```nginx
# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL certificates (managed by certbot)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' wss: https:;" always;

    # Frontend (React/Vite)
    location / {
        root /opt/edusense/frontend/dist;
        try_files $uri $uri/ /index.html;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for chat streaming
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # Static files (uploads, avatars, videos)
    location /static/ {
        alias /opt/edusense/backend/static/;
        expires 30d;
        add_header Cache-Control "public";
    }

    # Health check endpoint
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
```

### Enable Site and Get Certificates

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/edusense /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Get Let's Encrypt certificates
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

### Auto-renewal

Certbot installs a systemd timer. Verify it's active:

```bash
systemctl list-timers | grep certbot
```

## Option 2: Caddy (Simpler Configuration)

### Installation

```bash
# Ubuntu/Debian
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

### Caddyfile

```caddy
your-domain.com {
    # Automatic HTTPS via Let's Encrypt
    tls your-email@example.com

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
        Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' wss: https:;"
    }

    # Frontend
    root * /opt/edusense/frontend/dist
    try_files {path} /index.html
    file_server

    # Backend API
    handle_path /api/* {
        reverse_proxy 127.0.0.1:8000 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # Static files
    handle /static/* {
        root * /opt/edusense/backend
        file_server
    }
}
```

### Run Caddy

```bash
sudo systemctl enable caddy
sudo systemctl start caddy
```

## Option 3: Cloud Load Balancer (AWS ALB, GCP Cloud Load Balancing, Azure Front Door)

### AWS Application Load Balancer

1. Create an ALB with HTTPS listener (port 443)
2. Attach ACM certificate for your domain
3. Configure target group pointing to EC2 instances on port 8000
4. Enable HTTP->HTTPS redirect on port 80 listener
5. Configure security headers via CloudFront Functions or Lambda@Edge if needed

### GCP Cloud Load Balancing

1. Create a managed SSL certificate in GCP
2. Set up HTTPS load balancer with backend service pointing to instance group
3. Configure URL map for `/api/*` to backend, `/` to frontend bucket
4. Enable CDN for static assets

## Environment Variables for Production

Update your `.env` or environment configuration:

```bash
# Required for production
EDUSENSE_SECRET_KEY="your-very-long-random-secret-key-min-32-chars"
EDUSENSE_DATABASE_URL="postgresql://user:pass@host:5432/edusense"
EDUSENSE_AI_PROVIDER="gemini"
EDUSENSE_GEMINI_API_KEY="your-gemini-api-key"
EDUSENSE_TAVILY_API_KEY="your-tavily-api-key"
EDUSENSE_FRONTEND_URL="https://your-domain.com"
EDUSENSE_CORS_ORIGINS="https://your-domain.com,https://www.your-domain.com"
EDUSENSE_DISABLE_DEFAULT_ACCOUNTS="true"

# Email (for password reset)
EDUSENSE_SMTP_HOST="smtp.your-provider.com"
EDUSENSE_SMTP_PORT="587"
EDUSENSE_SMTP_USER="your-smtp-user"
EDUSENSE_SMTP_PASSWORD="your-smtp-password"
EDUSENSE_SMTP_FROM_EMAIL="noreply@your-domain.com"

# Vector store
EDUSENSE_CHROMA_PERSIST_DIR="/opt/edusense/data/chroma"
```

## Security Headers Explained

| Header | Purpose |
|--------|---------|
| `Strict-Transport-Security` | Forces HTTPS for 1 year, includes subdomains |
| `X-Frame-Options: DENY` | Prevents clickjacking |
| `X-Content-Type-Options: nosniff` | Prevents MIME sniffing |
| `X-XSS-Protection` | Legacy XSS filter (some browsers) |
| `Referrer-Policy` | Controls referrer information |
| `Content-Security-Policy` | Restricts resource loading to prevent XSS |

## TLS Configuration Best Practices

1. **Use TLS 1.2+ only** — Disable TLS 1.0, 1.1
2. **Prefer ECDHE cipher suites** — Forward secrecy
3. **Enable OCSP Stapling** — Faster certificate validation
4. **Use strong DH parameters** (nginx: `ssl_dhparam /etc/ssl/certs/dhparam.pem;`)
5. **Monitor certificate expiry** — Set up alerts for 30/14/7 days before expiry

## Testing Your Configuration

### SSL Labs Test

```bash
# Online test
https://www.ssllabs.com/ssltest/analyze.html?d=your-domain.com
```

### curl Tests

```bash
# Check headers
curl -I https://your-domain.com

# Check TLS version
curl --tlsv1.2 https://your-domain.com
curl --tlsv1.3 https://your-domain.com

# Should fail
curl --tlsv1.1 https://your-domain.com
```

### Security Headers Check

```bash
# Check CSP
curl -I https://your-domain.com | grep -i content-security-policy

# Check HSTS
curl -I https://your-domain.com | grep -i strict-transport-security
```

## Docker Production Deployment

If using Docker Compose in production, add a reverse proxy container:

```yaml
# docker-compose.prod.yml
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend
      - frontend

  backend:
    build: ./backend
    environment:
      - EDUSENSE_SECRET_KEY=${EDUSENSE_SECRET_KEY}
      - EDUSENSE_DATABASE_URL=${EDUSENSE_DATABASE_URL}
      # ... other env vars
    volumes:
      - ./backend/static:/app/static
      - ./backend/data/chroma:/app/data/chroma

  frontend:
    build: ./frontend
    # Build-time env vars for Vite

volumes:
  caddy_data:
  caddy_config:
```

## Troubleshooting

### Certificate Issues

```bash
# Check certificate details
openssl x509 -in /etc/letsencrypt/live/your-domain.com/fullchain.pem -text -noout

# Test certificate chain
openssl s_client -connect your-domain.com:443 -servername your-domain.com
```

### Mixed Content Errors

Ensure all frontend assets use relative URLs or HTTPS. Check `frontend_url` and `cors_origins` use `https://`.

### WebSocket Connection Issues

Ensure reverse proxy passes `Upgrade` and `Connection` headers for `/api/chat/stream` endpoint.

## Compliance Notes

- **GDPR**: TLS 1.2+ is required for personal data transmission
- **HIPAA**: If handling health data, ensure TLS 1.2+ and audit logging
- **PCI DSS**: Requires TLS 1.2+, no SSL/TLS 1.0/1.1, certificate validation

---

*Last updated: 2026-11-07*