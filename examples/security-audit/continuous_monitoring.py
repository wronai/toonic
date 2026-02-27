#!/usr/bin/env python3
"""
Continuous Security Monitoring for obywatel.bielik.ai

This script provides ongoing security monitoring, alerting, and reporting
for the obywatel.bielik.ai website. It integrates with the Toonic framework
and provides automated security checks.

Usage:
    python3 continuous_monitoring.py [--config config.yaml] [--daemon]
"""

import asyncio
import json
import logging
import smtplib
import yaml
from datetime import datetime, timedelta
from email.mime.text import MimeText
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import aiohttp
import ssl
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('security_monitoring.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SecurityMonitor:
    """Continuous security monitoring system."""
    
    def __init__(self, config_file: str = "monitoring_config.yaml"):
        self.config = self.load_config(config_file)
        self.domain = self.config.get('domain', 'obywatel.bielik.ai')
        self.alerts_sent = []
        self.monitoring_data = []
        
    def load_config(self, config_file: str) -> Dict:
        """Load monitoring configuration."""
        default_config = {
            'domain': 'obywatel.bielik.ai',
            'check_interval': 300,  # 5 minutes
            'alert_threshold': {
                'ssl_expiry_days': 30,
                'response_time_ms': 2000,
                'security_headers_missing': 2
            },
            'notifications': {
                'email': {
                    'enabled': False,
                    'smtp_server': 'smtp.gmail.com',
                    'smtp_port': 587,
                    'username': '',
                    'password': '',
                    'recipients': []
                },
                'webhook': {
                    'enabled': False,
                    'url': ''
                }
            },
            'checks': {
                'ssl_certificate': True,
                'security_headers': True,
                'response_time': True,
                'content_changes': True,
                'dependency_check': True
            }
        }
        
        config_path = Path(config_file)
        if config_path.exists():
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f)
                default_config.update(user_config)
        else:
            # Create default config file
            with open(config_path, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False)
            logger.info(f"Created default config file: {config_path}")
            
        return default_config
    
    async def check_ssl_certificate(self) -> Dict:
        """Check SSL certificate validity and configuration."""
        result = {
            'check': 'ssl_certificate',
            'timestamp': datetime.now().isoformat(),
            'status': 'pass',
            'issues': [],
            'details': {}
        }
        
        try:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://{self.domain}', ssl=context) as response:
                    ssl_info = response.connection.get_extra_info('ssl_object')
                    if ssl_info:
                        cert = ssl_info.getpeercert()
                        
                        # Check certificate expiry
                        expiry_date = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                        days_to_expiry = (expiry_date - datetime.now()).days
                        
                        result['details'] = {
                            'expiry_date': expiry_date.isoformat(),
                            'days_to_expiry': days_to_expiry,
                            'issuer': cert['issuer'],
                            'subject': cert['subject']
                        }
                        
                        if days_to_expiry < self.config['alert_threshold']['ssl_expiry_days']:
                            result['status'] = 'fail'
                            result['issues'].append(f'Certificate expires in {days_to_expiry} days')
                        
                        # Check SSL version
                        ssl_version = ssl_info.version()
                        if ssl_version in ['SSLv2', 'SSLv3', 'TLSv1', 'TLSv1.1']:
                            result['status'] = 'fail'
                            result['issues'].append(f'Insecure SSL version: {ssl_version}')
                            
        except Exception as e:
            result['status'] = 'error'
            result['issues'].append(f'SSL check failed: {str(e)}')
            
        return result
    
    async def check_security_headers(self) -> Dict:
        """Check for security headers."""
        result = {
            'check': 'security_headers',
            'timestamp': datetime.now().isoformat(),
            'status': 'pass',
            'issues': [],
            'details': {}
        }
        
        required_headers = [
            'content-security-policy',
            'x-frame-options',
            'x-content-type-options',
            'referrer-policy',
            'strict-transport-security',
            'permissions-policy'
        ]
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://{self.domain}') as response:
                    headers = dict(response.headers)
                    present_headers = []
                    missing_headers = []
                    
                    for header in required_headers:
                        if header in headers:
                            present_headers.append(header)
                        else:
                            missing_headers.append(header)
                    
                    result['details'] = {
                        'present_headers': present_headers,
                        'missing_headers': missing_headers,
                        'total_headers': len(present_headers),
                        'required_headers': len(required_headers)
                    }
                    
                    if len(missing_headers) >= self.config['alert_threshold']['security_headers_missing']:
                        result['status'] = 'fail'
                        result['issues'].append(f'Too many missing headers: {missing_headers}')
                        
        except Exception as e:
            result['status'] = 'error'
            result['issues'].append(f'Security headers check failed: {str(e)}')
            
        return result
    
    async def check_response_time(self) -> Dict:
        """Check website response time."""
        result = {
            'check': 'response_time',
            'timestamp': datetime.now().isoformat(),
            'status': 'pass',
            'issues': [],
            'details': {}
        }
        
        try:
            start_time = datetime.now()
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://{self.domain}') as response:
                    end_time = datetime.now()
                    response_time_ms = (end_time - start_time).total_seconds() * 1000
                    
                    result['details'] = {
                        'response_time_ms': round(response_time_ms, 2),
                        'status_code': response.status,
                        'content_length': response.headers.get('content-length', 0)
                    }
                    
                    if response_time_ms > self.config['alert_threshold']['response_time_ms']:
                        result['status'] = 'fail'
                        result['issues'].append(f'Response time too high: {response_time_ms}ms')
                        
        except Exception as e:
            result['status'] = 'error'
            result['issues'].append(f'Response time check failed: {str(e)}')
            
        return result
    
    async def check_content_changes(self) -> Dict:
        """Check for unexpected content changes."""
        result = {
            'check': 'content_changes',
            'timestamp': datetime.now().isoformat(),
            'status': 'pass',
            'issues': [],
            'details': {}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://{self.domain}') as response:
                    content = await response.text()
                    
                    # Simple hash for content comparison
                    content_hash = hash(content)
                    result['details'] = {
                        'content_hash': content_hash,
                        'content_length': len(content),
                        'status_code': response.status
                    }
                    
                    # Check for development URLs
                    if 'localhost' in content.lower():
                        result['status'] = 'fail'
                        result['issues'].append('Development URLs found in production content')
                    
                    # Check for error indicators
                    error_indicators = ['internal server error', 'database error', 'stack trace']
                    for indicator in error_indicators:
                        if indicator in content.lower():
                            result['status'] = 'fail'
                            result['issues'].append(f'Error indicator found: {indicator}')
                            
        except Exception as e:
            result['status'] = 'error'
            result['issues'].append(f'Content check failed: {str(e)}')
            
        return result
    
    async def check_dependencies(self) -> Dict:
        """Check external dependencies for security issues."""
        result = {
            'check': 'dependency_check',
            'timestamp': datetime.now().isoformat(),
            'status': 'pass',
            'issues': [],
            'details': {}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'https://{self.domain}') as response:
                    content = await response.text()
                    
                    # Check for external dependencies
                    external_deps = []
                    cdn_patterns = [
                        'cdn.jsdelivr.net',
                        'fonts.googleapis.com',
                        'fonts.gstatic.com',
                        'cdnjs.cloudflare.com'
                    ]
                    
                    for pattern in cdn_patterns:
                        if pattern in content:
                            external_deps.append(pattern)
                    
                    result['details'] = {
                        'external_dependencies': external_deps,
                        'dependency_count': len(external_deps)
                    }
                    
                    # Check for SRI hashes
                    if 'integrity' in content and external_deps:
                        sri_count = content.count('integrity=')
                        result['details']['sri_hashes'] = sri_count
                        result['details']['sri_coverage'] = f"{sri_count}/{len(external_deps)}"
                    else:
                        result['details']['sri_hashes'] = 0
                        result['details']['sri_coverage'] = "0/0"
                        
        except Exception as e:
            result['status'] = 'error'
            result['issues'].append(f'Dependency check failed: {str(e)}')
            
        return result
    
    async def run_all_checks(self) -> List[Dict]:
        """Run all security checks."""
        checks = []
        
        if self.config['checks']['ssl_certificate']:
            checks.append(await self.check_ssl_certificate())
        
        if self.config['checks']['security_headers']:
            checks.append(await self.check_security_headers())
        
        if self.config['checks']['response_time']:
            checks.append(await self.check_response_time())
        
        if self.config['checks']['content_changes']:
            checks.append(await self.check_content_changes())
        
        if self.config['checks']['dependency_check']:
            checks.append(await self.check_dependencies())
        
        return checks
    
    def calculate_security_score(self, checks: List[Dict]) -> int:
        """Calculate overall security score."""
        if not checks:
            return 0
        
        total_score = 0
        max_score = len(checks) * 100
        
        for check in checks:
            if check['status'] == 'pass':
                total_score += 100
            elif check['status'] == 'fail':
                total_score += 50
            # error gets 0 points
        
        return int((total_score / max_score) * 100)
    
    async def send_alert(self, check_results: List[Dict]):
        """Send security alerts."""
        failed_checks = [check for check in check_results if check['status'] in ['fail', 'error']]
        
        if not failed_checks:
            return
        
        # Check if we've already sent an alert for these issues
        alert_key = hash(str(failed_checks))
        if alert_key in self.alerts_sent:
            return
        
        self.alerts_sent.append(alert_key)
        
        # Prepare alert message
        subject = f"🚨 Security Alert for {self.domain}"
        message = f"Security monitoring detected issues:\n\n"
        
        for check in failed_checks:
            message += f"❌ {check['check']}: {check['status']}\n"
            for issue in check['issues']:
                message += f"  • {issue}\n"
            message += "\n"
        
        message += f"Timestamp: {datetime.now().isoformat()}\n"
        message += f"Security Score: {self.calculate_security_score(check_results)}/100\n"
        
        # Send email alert
        if self.config['notifications']['email']['enabled']:
            await self.send_email_alert(subject, message)
        
        # Send webhook alert
        if self.config['notifications']['webhook']['enabled']:
            await self.send_webhook_alert(subject, message)
    
    async def send_email_alert(self, subject: str, message: str):
        """Send email alert."""
        try:
            email_config = self.config['notifications']['email']
            
            msg = MimeText(message)
            msg['Subject'] = subject
            msg['From'] = email_config['username']
            msg['To'] = ', '.join(email_config['recipients'])
            
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['username'], email_config['password'])
                server.send_message(msg)
            
            logger.info("Email alert sent successfully")
            
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
    
    async def send_webhook_alert(self, subject: str, message: str):
        """Send webhook alert."""
        try:
            webhook_config = self.config['notifications']['webhook']
            
            payload = {
                'text': f"**{subject}**\n\n{message}",
                'domain': self.domain,
                'timestamp': datetime.now().isoformat(),
                'severity': 'high'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_config['url'], json=payload) as response:
                    if response.status == 200:
                        logger.info("Webhook alert sent successfully")
                    else:
                        logger.error(f"Webhook alert failed: {response.status}")
                        
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
    
    def save_monitoring_data(self, check_results: List[Dict]):
        """Save monitoring data to file."""
        data_point = {
            'timestamp': datetime.now().isoformat(),
            'security_score': self.calculate_security_score(check_results),
            'checks': check_results
        }
        
        self.monitoring_data.append(data_point)
        
        # Keep only last 1000 data points
        if len(self.monitoring_data) > 1000:
            self.monitoring_data = self.monitoring_data[-1000:]
        
        # Save to file
        with open('monitoring_data.json', 'w') as f:
            json.dump(self.monitoring_data, f, indent=2)
    
    async def run_monitoring_cycle(self):
        """Run one monitoring cycle."""
        logger.info(f"Starting monitoring cycle for {self.domain}")
        
        # Run all checks
        check_results = await self.run_all_checks()
        
        # Calculate security score
        security_score = self.calculate_security_score(check_results)
        
        # Log results
        logger.info(f"Security score: {security_score}/100")
        for check in check_results:
            if check['status'] != 'pass':
                logger.warning(f"{check['check']}: {check['status']} - {check['issues']}")
        
        # Send alerts if needed
        await self.send_alert(check_results)
        
        # Save monitoring data
        self.save_monitoring_data(check_results)
        
        return check_results
    
    async def start_daemon(self):
        """Start continuous monitoring daemon."""
        logger.info(f"Starting security monitoring daemon for {self.domain}")
        logger.info(f"Check interval: {self.config['check_interval']} seconds")
        
        while True:
            try:
                await self.run_monitoring_cycle()
                await asyncio.sleep(self.config['check_interval'])
            except KeyboardInterrupt:
                logger.info("Monitoring daemon stopped by user")
                break
            except Exception as e:
                logger.error(f"Monitoring cycle failed: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying

async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Continuous Security Monitoring")
    parser.add_argument('--config', default='monitoring_config.yaml', help='Configuration file')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    parser.add_argument('--once', action='store_true', help='Run single check cycle')
    
    args = parser.parse_args()
    
    monitor = SecurityMonitor(args.config)
    
    if args.daemon:
        await monitor.start_daemon()
    elif args.once:
        results = await monitor.run_monitoring_cycle()
        print(f"Security Score: {monitor.calculate_security_score(results)}/100")
        for result in results:
            print(f"{result['check']}: {result['status']}")
            if result['issues']:
                for issue in result['issues']:
                    print(f"  - {issue}")
    else:
        # Interactive mode
        print("🔒 Security Monitoring for obywatel.bielik.ai")
        print("=" * 50)
        results = await monitor.run_monitoring_cycle()
        
        print(f"\n📊 Security Score: {monitor.calculate_security_score(results)}/100")
        print("\n🔍 Check Results:")
        for result in results:
            status_emoji = "✅" if result['status'] == 'pass' else "❌" if result['status'] == 'fail' else "⚠️"
            print(f"{status_emoji} {result['check'].replace('_', ' ').title()}: {result['status'].upper()}")
            if result['issues']:
                for issue in result['issues']:
                    print(f"   • {issue}")

if __name__ == "__main__":
    asyncio.run(main())
