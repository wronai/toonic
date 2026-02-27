#!/bin/bash
# Install Requirements for Security Audit Package

echo "🔧 Installing system requirements..."
echo "=================================="

# Update package list
echo "Updating package list..."
sudo apt update

# Install required packages
echo "Installing required packages..."
sudo apt install -y nginx curl openssl jq python3-pip python3-venv

# Install Python packages
echo "Installing Python packages..."
sudo pip3 install aiohttp pyyaml

# Start nginx (if not running)
echo "Starting nginx..."
sudo systemctl start nginx
sudo systemctl enable nginx

# Verify installation
echo "Verifying installation..."
echo "nginx version: $(nginx -v 2>&1)"
echo "curl version: $(curl --version | head -n1)"
echo "openssl version: $(openssl version)"
echo "jq version: $(jq --version)"
echo "python3 version: $(python3 --version)"

echo ""
echo "✅ All requirements installed successfully!"
echo ""
echo "Now you can run:"
echo "sudo ./QUICK_DEPLOYMENT.sh"
