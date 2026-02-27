#!/bin/bash
# Quick Deployment Script - Complete Security Audit Package
# One-command deployment of all security tools and configurations

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="obywatel.bielik.ai"
INSTALL_DIR="/opt/security-audit"
SERVICE_USER="security-monitor"

print_header() {
    echo -e "${BLUE}"
    echo "=================================================="
    echo "🔒 Complete Security Audit Package Deployment"
    echo "=================================================="
    echo -e "${NC}"
    echo "Target: $DOMAIN"
    echo "Install Directory: $INSTALL_DIR"
    echo "Service User: $SERVICE_USER"
    echo ""
}

print_step() {
    echo -e "${GREEN}[STEP]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    print_step "Checking system requirements..."
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
    
    # Check required packages
    required_packages=("python3" "nginx" "curl" "openssl" "jq")
    missing_packages=()
    
    for package in "${required_packages[@]}"; do
        if ! command -v "$package" &> /dev/null; then
            missing_packages+=("$package")
        fi
    done
    
    if [ ${#missing_packages[@]} -ne 0 ]; then
        print_error "Missing required packages: ${missing_packages[*]}"
        print_info "Install with: apt update && apt install -y ${missing_packages[*]}"
        exit 1
    fi
    
    # Check Python packages
    python_packages=("aiohttp" "yaml" "asyncio")
    for package in "${python_packages[@]}"; do
        if ! python3 -c "import $package" &> /dev/null; then
            print_warning "Python package '$package' not found"
            print_info "Installing with: pip3 install $package aiohttp pyyaml"
            pip3 install $package aiohttp pyyaml
        fi
    done
    
    print_info "✅ All requirements satisfied"
}

create_directories() {
    print_step "Creating directory structure..."
    
    # Create main directory
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    # Create subdirectories
    mkdir -p {logs,backups,config,reports,scripts}
    
    # Set permissions
    chown -R root:root "$INSTALL_DIR"
    chmod 755 "$INSTALL_DIR"
    
    print_info "✅ Directory structure created"
}

install_tools() {
    print_step "Installing security tools..."
    
    # Get current script directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Copy all files to install directory
    if [ -d "$SCRIPT_DIR" ]; then
        cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
        print_info "✅ Tools copied from $SCRIPT_DIR"
    else
        print_error "Source directory not found: $SCRIPT_DIR"
        exit 1
    fi
    
    # Make scripts executable
    chmod +x "$INSTALL_DIR"/*.sh
    chmod +x "$INSTALL_DIR"/*.py
    
    print_info "✅ Security tools installed"
}

setup_service_user() {
    print_step "Setting up service user..."
    
    # Create service user if not exists
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
        print_info "✅ Service user created: $SERVICE_USER"
    else
        print_info "✅ Service user already exists: $SERVICE_USER"
    fi
    
    # Set ownership for monitoring files
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"/{logs,backups,reports}
    chmod 755 "$INSTALL_DIR"/{logs,backups,reports}
}

configure_monitoring() {
    print_step "Configuring monitoring..."
    
    # Update monitoring config with correct paths
    sed -i "s|security_monitoring.log|$INSTALL_DIR/logs/security_monitoring.log|g" "$INSTALL_DIR/monitoring_config.yaml"
    sed -i "s|./backups/|$INSTALL_DIR/backups/|g" "$INSTALL_DIR/monitoring_config.yaml"
    
    # Create systemd service for continuous monitoring
    cat > "/etc/systemd/system/security-monitor.service" << EOF
[Unit]
Description=Security Monitoring Service for $DOMAIN
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/continuous_monitoring.py --daemon --config $INSTALL_DIR/monitoring_config.yaml
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable security-monitor.service
    
    print_info "✅ Monitoring configured and service enabled"
}

setup_nginx() {
    print_step "Configuring nginx..."
    
    # Backup current nginx config
    if [ -f "/etc/nginx/sites-available/$DOMAIN" ]; then
        cp "/etc/nginx/sites-available/$DOMAIN" "$INSTALL_DIR/backups/nginx_$(date +%Y%m%d_%H%M%S)"
        print_info "✅ Current nginx config backed up"
    fi
    
    # Copy remediation script to system location
    cp "$INSTALL_DIR/remediation_script.sh" "/usr/local/bin/security-remediation.sh"
    chmod +x "/usr/local/bin/security-remediation.sh"
    
    print_info "✅ Nginx configuration ready"
    print_warning "Run 'sudo /usr/local/bin/security-remediation.sh' to apply security headers"
}

setup_cron_jobs() {
    print_step "Setting up scheduled tasks..."
    
    # Create cron jobs
    (crontab -l 2>/dev/null; echo "# Security monitoring tasks") | crontab -
    (crontab -l 2>/dev/null; echo "0 6 * * * $INSTALL_DIR/continuous_monitoring.py --once >> $INSTALL_DIR/logs/daily_check.log 2>&1") | crontab -
    (crontab -l 2>/dev/null; echo "0 0 * * 0 $INSTALL_DIR/generate_report.py --data-dir $INSTALL_DIR/reports --output $INSTALL_DIR/reports/weekly_report_\$(date +\%Y\%m\%d).md") | crontab -
    (crontab -l 2>/dev/null; echo "0 2 * * * find $INSTALL_DIR/logs -name '*.log' -mtime +30 -delete") | crontab -
    (crontab -l 2>/dev/null; echo "0 3 * * * find $INSTALL_DIR/backups -name '*' -mtime +90 -delete") | crontab -
    
    print_info "✅ Cron jobs configured"
}

setup_logrotate() {
    print_step "Setting up log rotation..."
    
    # Create logrotate configuration
    cat > "/etc/logrotate.d/security-monitor" << EOF
$INSTALL_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload security-monitor.service || true
    endscript
}
EOF
    
    print_info "✅ Log rotation configured"
}

create_management_scripts() {
    print_step "Creating management scripts..."
    
    # Status script
    cat > "$INSTALL_DIR/scripts/status.sh" << 'EOF'
#!/bin/bash
echo "🔒 Security Monitoring Status"
echo "============================="
echo "Service: $(systemctl is-active security-monitor.service)"
echo "Enabled: $(systemctl is-enabled security-monitor.service)"
echo "Last check: $(tail -1 /opt/security-audit/logs/security_monitoring.log 2>/dev/null | cut -d' ' -f1-3 || echo 'Never')"
echo "Log size: $(du -sh /opt/security-audit/logs/ 2>/dev/null | cut -f1 || echo 'Unknown')"
echo ""
echo "📊 Recent Alerts:"
tail -10 /opt/security-audit/logs/security_monitoring.log 2>/dev/null | grep -i "alert\|fail\|error" || echo "No recent alerts"
EOF
    
    # Quick scan script
    cat > "$INSTALL_DIR/scripts/quick_scan.sh" << 'EOF'
#!/bin/bash
echo "🔍 Quick Security Scan"
echo "===================="
cd /opt/security-audit
python3 continuous_monitoring.py --once
echo ""
echo "📄 Generate report:"
python3 generate_report.py --data-dir /opt/security-audit/reports --output "quick_scan_$(date +%Y%m%d_%H%M%S).md"
EOF
    
    # Dashboard launcher
    cat > "$INSTALL_DIR/scripts/dashboard.sh" << 'EOF'
#!/bin/bash
echo "🌐 Launching Security Dashboard..."
cd /opt/security-audit
python3 -m http.server 8080 > /dev/null 2>&1 &
echo "Dashboard available at: http://localhost:8080/security_dashboard.html"
echo "Press Ctrl+C to stop the server"
sleep 2
xdg-open http://localhost:8080/security_dashboard.html 2>/dev/null || open http://localhost:8080/security_dashboard.html 2>/dev/null
python3 -m http.server 8080
EOF
    
    # Make scripts executable
    chmod +x "$INSTALL_DIR/scripts/*.sh"
    
    print_info "✅ Management scripts created"
}

run_initial_tests() {
    print_step "Running initial security tests..."
    
    cd "$INSTALL_DIR"
    
    # Test SSL certificate
    print_info "Testing SSL certificate..."
    if echo | openssl s_client -connect "$DOMAIN":443 -servername "$DOMAIN" 2>/dev/null | grep -q "Verify return code: 0 (ok)"; then
        print_info "✅ SSL certificate valid"
    else
        print_warning "⚠️ SSL certificate issue detected"
    fi
    
    # Test HTTP response
    print_info "Testing HTTP response..."
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN" || echo "000")
    if [ "$HTTP_STATUS" = "200" ]; then
        print_info "✅ Website responding (HTTP $HTTP_STATUS)"
    else
        print_warning "⚠️ Website not responding (HTTP $HTTP_STATUS)"
    fi
    
    # Test security headers
    print_info "Testing security headers..."
    HEADERS_COUNT=$(curl -s -I "https://$DOMAIN" 2>/dev/null | grep -i -c -E "(content-security-policy|x-frame-options|x-content-type-options|strict-transport-security)" || echo "0")
    print_info "Security headers found: $HEADERS_COUNT/6"
    
    # Run one monitoring cycle
    print_info "Running monitoring test..."
    python3 continuous_monitoring.py --once > /dev/null 2>&1
    
    print_info "✅ Initial tests completed"
}

start_services() {
    print_step "Starting security services..."
    
    # Start monitoring service
    systemctl start security-monitor.service
    
    # Wait a moment and check status
    sleep 3
    if systemctl is-active --quiet security-monitor.service; then
        print_info "✅ Security monitoring service started"
    else
        print_error "❌ Security monitoring service failed to start"
        print_info "Check logs: journalctl -u security-monitor.service"
    fi
}

print_summary() {
    echo ""
    echo -e "${GREEN}"
    echo "🎉 Security Audit Package Deployment Complete!"
    echo "============================================"
    echo -e "${NC}"
    echo ""
    echo "📍 Installation Directory: $INSTALL_DIR"
    echo "🔧 Management Scripts: $INSTALL_DIR/scripts/"
    echo "📊 Dashboard: http://localhost:8080/security_dashboard.html"
    echo "📋 Configuration: $INSTALL_DIR/monitoring_config.yaml"
    echo ""
    echo "🚀 Quick Commands:"
    echo "  • Status: $INSTALL_DIR/scripts/status.sh"
    echo "  • Quick Scan: $INSTALL_DIR/scripts/quick_scan.sh"
    echo "  • Dashboard: $INSTALL_DIR/scripts/dashboard.sh"
    echo "  • Apply Fixes: sudo /usr/local/bin/security-remediation.sh"
    echo ""
    echo "📊 Service Management:"
    echo "  • Start: sudo systemctl start security-monitor.service"
    echo "  • Stop: sudo systemctl stop security-monitor.service"
    echo "  • Status: sudo systemctl status security-monitor.service"
    echo "  • Logs: sudo journalctl -u security-monitor.service -f"
    echo ""
    echo "📁 Important Files:"
    echo "  • Config: $INSTALL_DIR/monitoring_config.yaml"
    echo "  • Logs: $INSTALL_DIR/logs/security_monitoring.log"
    echo "  • Reports: $INSTALL_DIR/reports/"
    echo "  • Backups: $INSTALL_DIR/backups/"
    echo ""
    echo "⚠️  Next Steps:"
    echo "  1. Review monitoring configuration: $INSTALL_DIR/monitoring_config.yaml"
    echo "  2. Configure email/webhook notifications"
    echo "  3. Apply security fixes: sudo /usr/local/bin/security-remediation.sh"
    echo "  4. Open dashboard: $INSTALL_DIR/scripts/dashboard.sh"
    echo ""
    echo -e "${GREEN}✅ Security monitoring is now active!${NC}"
    echo ""
}

# Main execution
main() {
    print_header
    
    check_requirements
    create_directories
    install_tools
    setup_service_user
    configure_monitoring
    setup_nginx
    setup_cron_jobs
    setup_logrotate
    create_management_scripts
    run_initial_tests
    start_services
    print_summary
}

# Run main function
main "$@"
