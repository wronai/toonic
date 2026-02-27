# Manual Installation Guide

## 📋 Required Packages Installation

The deployment script requires several packages to be installed. Here's how to install them manually:

### Step 1: Update System Packages
```bash
sudo apt update
```

### Step 2: Install Required Packages
```bash
sudo apt install -y nginx curl openssl jq python3-pip python3-venv
```

### Step 3: Install Python Dependencies
```bash
sudo pip3 install aiohttp pyyaml
```

### Step 4: Start and Enable Nginx
```bash
sudo systemctl start nginx
sudo systemctl enable nginx
```

### Step 5: Verify Installation
```bash
# Check nginx
nginx -v

# Check curl
curl --version | head -n1

# Check openssl
openssl version

# Check jq
jq --version

# Check python3
python3 --version
```

## 🚀 Quick Installation Commands

Copy and paste these commands:

```bash
# One-liner installation
sudo apt update && sudo apt install -y nginx curl openssl jq python3-pip python3-venv && sudo pip3 install aiohttp pyyaml && sudo systemctl start nginx && sudo systemctl enable nginx

# Or use the provided script
chmod +x INSTALL_REQUIREMENTS.sh
sudo ./INSTALL_REQUIREMENTS.sh
```

## 🔧 Alternative: Without Root Access

If you don't have sudo access, you can still use the security audit tools:

### Option 1: Use Python-only monitoring
```bash
# Install Python packages locally
pip3 install --user aiohttp pyyaml

# Run monitoring without systemd service
python3 continuous_monitoring.py --once

# Generate reports
python3 generate_report.py --data-dir ../../toonic_data
```

### Option 2: Use Docker (if available)
```bash
# Create Dockerfile for security monitoring
cat > Dockerfile << 'EOF'
FROM python:3.9-slim
RUN apt-get update && apt-get install -y curl openssl jq nginx
RUN pip3 install aiohttp pyyaml
COPY . /app
WORKDIR /app
CMD ["python3", "continuous_monitoring.py", "--daemon"]
EOF

# Build and run
docker build -t security-monitor .
docker run -p 8080:8080 security-monitor
```

## 📊 Package Explanations

| Package | Purpose | Required For |
|---------|---------|--------------|
| `nginx` | Web server for security headers | Remediation script |
| `curl` | HTTP requests testing | Monitoring & testing |
| `openssl` | SSL/TLS testing | Certificate checks |
| `jq` | JSON processing | Log analysis |
| `python3-pip` | Python package manager | Python dependencies |
| `aiohttp` | Async HTTP client | Continuous monitoring |
| `pyyaml` | YAML configuration | Config file parsing |

## 🛠️ Post-Installation Steps

After installing packages:

### 1. Run the deployment script
```bash
sudo ./QUICK_DEPLOYMENT.sh
```

### 2. Verify installation
```bash
# Check service status
sudo systemctl status security-monitor.service

# Check monitoring logs
sudo journalctl -u security-monitor.service -f

# Test security headers
curl -I https://obywatel.bielik.ai
```

### 3. Access the dashboard
```bash
# Start local server
python3 -m http.server 8080

# Open in browser
open http://localhost:8080/security_dashboard.html
```

## 🔍 Troubleshooting

### Common Issues

#### 1. "Permission denied" errors
```bash
# Make sure you're using sudo
sudo ./QUICK_DEPLOYMENT.sh

# Or check file permissions
ls -la QUICK_DEPLOYMENT.sh
chmod +x QUICK_DEPLOYMENT.sh
```

#### 2. "nginx: command not found"
```bash
# Install nginx
sudo apt install nginx

# Check if nginx is running
sudo systemctl status nginx
```

#### 3. Python package errors
```bash
# Install packages with --user flag
pip3 install --user aiohttp pyyaml

# Or use virtual environment
python3 -m venv security-env
source security-env/bin/activate
pip install aiohttp pyyaml
```

#### 4. Port conflicts
```bash
# Check what's using port 8080
sudo netstat -tlnp | grep :8080

# Kill the process
sudo kill -9 <PID>

# Or use different port
python3 -m http.server 8081
```

## 📞 Getting Help

If you encounter issues:

1. **Check system requirements:**
   ```bash
   python3 --version  # Should be 3.7+
   nginx -v           # Should be recent version
   ```

2. **Verify package installation:**
   ```bash
   dpkg -l | grep nginx
   pip3 list | grep aiohttp
   ```

3. **Check logs:**
   ```bash
   # Nginx logs
   sudo tail -f /var/log/nginx/error.log
   
   # Security monitor logs
   sudo journalctl -u security-monitor.service -f
   ```

4. **Manual testing:**
   ```bash
   # Test SSL
   openssl s_client -connect obywatel.bielik.ai:443
   
   # Test headers
   curl -I https://obywatel.bielik.ai
   
   # Test monitoring
   python3 continuous_monitoring.py --once
   ```

## 🚀 Minimal Installation

For testing purposes, you can run with minimal requirements:

```bash
# Just Python packages (no root needed)
pip3 install aiohttp pyyaml

# Run basic monitoring
python3 continuous_monitoring.py --once

# Generate report
python3 generate_report.py --data-dir ../../toonic_data

# Open dashboard
python3 -m http.server 8080 &
open http://localhost:8080/security_dashboard.html
```

This gives you:
- ✅ Security monitoring
- ✅ Report generation  
- ✅ Interactive dashboard
- ❌ No system service
- ❌ No automated fixes
- ❌ No nginx configuration

## 📋 Installation Checklist

- [ ] System updated: `sudo apt update`
- [ ] Packages installed: `nginx curl openssl jq python3-pip`
- [ ] Python deps: `pip3 install aiohttp pyyaml`
- [ ] Nginx running: `sudo systemctl start nginx`
- [ ] Deployment script: `sudo ./QUICK_DEPLOYMENT.sh`
- [ ] Service active: `sudo systemctl status security-monitor`
- [ ] Dashboard accessible: `http://localhost:8080/security_dashboard.html`

---

**Once all packages are installed, run:**
```bash
sudo ./QUICK_DEPLOYMENT.sh
```

**For minimal setup (no sudo):**
```bash
pip3 install aiohttp pyyaml
python3 continuous_monitoring.py --once
```
