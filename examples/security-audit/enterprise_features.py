#!/usr/bin/env python3
"""
Enterprise Security Features for obywatel.bielik.ai

Advanced security monitoring with ML-based anomaly detection,
threat intelligence integration, and compliance automation.

Usage:
    python3 enterprise_features.py --config enterprise_config.yaml
"""

import asyncio
import json
import logging
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import aiohttp
import yaml
from dataclasses import dataclass, asdict
import hashlib
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class SecurityEvent:
    """Security event data structure."""
    timestamp: datetime
    event_type: str
    severity: str  # low, medium, high, critical
    source: str
    details: Dict[str, Any]
    confidence: float
    remediation: Optional[str] = None

@dataclass
class ThreatIntelligence:
    """Threat intelligence data structure."""
    indicator: str
    indicator_type: str  # ip, domain, hash, url
    threat_type: str
    confidence: float
    source: str
    first_seen: datetime
    last_seen: datetime
    tags: List[str]

@dataclass
class ComplianceCheck:
    """Compliance check result."""
    standard: str  # GDPR, ISO27001, SOC2, PCI-DSS
    control: str
    status: str  # compliant, non_compliant, partial
    evidence: List[str]
    risk_level: str
    remediation: str

class AnomalyDetector:
    """ML-based anomaly detection for security events."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.baseline_data = []
        self.anomaly_threshold = config.get('anomaly_threshold', 2.0)
        self.window_size = config.get('window_size', 100)
        
    def collect_baseline(self, metrics: List[Dict]):
        """Collect baseline metrics for anomaly detection."""
        self.baseline_data.extend(metrics)
        
        # Keep only recent data
        if len(self.baseline_data) > self.window_size * 10:
            self.baseline_data = self.baseline_data[-self.window_size * 10:]
    
    def detect_anomalies(self, current_metrics: List[Dict]) -> List[SecurityEvent]:
        """Detect anomalies in current metrics."""
        anomalies = []
        
        if len(self.baseline_data) < self.window_size:
            return anomalies
        
        # Calculate baseline statistics
        baseline_response_times = [m.get('response_time', 0) for m in self.baseline_data]
        baseline_error_rates = [m.get('error_rate', 0) for m in self.baseline_data]
        
        baseline_mean_rt = np.mean(baseline_response_times)
        baseline_std_rt = np.std(baseline_response_times)
        baseline_mean_er = np.mean(baseline_error_rates)
        baseline_std_er = np.std(baseline_error_rates)
        
        # Check current metrics
        for metric in current_metrics:
            response_time = metric.get('response_time', 0)
            error_rate = metric.get('error_rate', 0)
            
            # Detect response time anomalies
            if baseline_std_rt > 0:
                z_score_rt = abs(response_time - baseline_mean_rt) / baseline_std_rt
                if z_score_rt > self.anomaly_threshold:
                    anomalies.append(SecurityEvent(
                        timestamp=datetime.now(),
                        event_type="response_time_anomaly",
                        severity="medium" if z_score_rt < 3 else "high",
                        source="anomaly_detector",
                        details={
                            "response_time": response_time,
                            "baseline_mean": baseline_mean_rt,
                            "z_score": z_score_rt,
                            "threshold": self.anomaly_threshold
                        },
                        confidence=min(z_score_rt / self.anomaly_threshold, 1.0),
                        remediation="Investigate server performance and potential DoS attacks"
                    ))
            
            # Detect error rate anomalies
            if baseline_std_er > 0:
                z_score_er = abs(error_rate - baseline_mean_er) / baseline_std_er
                if z_score_er > self.anomaly_threshold:
                    anomalies.append(SecurityEvent(
                        timestamp=datetime.now(),
                        event_type="error_rate_anomaly",
                        severity="high" if error_rate > 0.1 else "medium",
                        source="anomaly_detector",
                        details={
                            "error_rate": error_rate,
                            "baseline_mean": baseline_mean_er,
                            "z_score": z_score_er,
                            "threshold": self.anomaly_threshold
                        },
                        confidence=min(z_score_er / self.anomaly_threshold, 1.0),
                        remediation="Check application logs for errors and potential security incidents"
                    ))
        
        return anomalies

class ThreatIntelligenceManager:
    """Threat intelligence integration and analysis."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.threat_feeds = config.get('threat_feeds', {})
        self.local_indicators = []
        
    async def fetch_threat_intelligence(self) -> List[ThreatIntelligence]:
        """Fetch threat intelligence from various feeds."""
        threats = []
        
        # Fetch from configured feeds
        for feed_name, feed_config in self.threat_feeds.items():
            try:
                if feed_config.get('enabled', False):
                    feed_threats = await self._fetch_feed(feed_name, feed_config)
                    threats.extend(feed_threats)
            except Exception as e:
                logger.error(f"Failed to fetch from threat feed {feed_name}: {e}")
        
        return threats
    
    async def _fetch_feed(self, feed_name: str, feed_config: Dict) -> List[ThreatIntelligence]:
        """Fetch threats from a specific feed."""
        # Simulated threat feed - in production, integrate with real feeds
        if feed_name == "malware_domains":
            return [
                ThreatIntelligence(
                    indicator="malicious-example.com",
                    indicator_type="domain",
                    threat_type="malware_c2",
                    confidence=0.9,
                    source="malware_domains_feed",
                    first_seen=datetime.now() - timedelta(days=30),
                    last_seen=datetime.now(),
                    tags=["malware", "c2", "command_and_control"]
                )
            ]
        return []
    
    def check_indicators(self, content: str, threats: List[ThreatIntelligence]) -> List[SecurityEvent]:
        """Check content against threat intelligence indicators."""
        events = []
        
        for threat in threats:
            if threat.indicator_type == "domain" and threat.indicator in content:
                events.append(SecurityEvent(
                    timestamp=datetime.now(),
                    event_type="threat_indicator_detected",
                    severity="high" if threat.confidence > 0.8 else "medium",
                    source="threat_intelligence",
                    details={
                        "indicator": threat.indicator,
                        "indicator_type": threat.indicator_type,
                        "threat_type": threat.threat_type,
                        "confidence": threat.confidence,
                        "source": threat.source
                    },
                    confidence=threat.confidence,
                    remediation=f"Block access to {threat.indicator} and investigate connections"
                ))
        
        return events

class ComplianceManager:
    """Compliance management and automation."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.standards = config.get('standards', {})
        
    def check_gdpr_compliance(self, security_headers: Dict, content: str) -> List[ComplianceCheck]:
        """Check GDPR compliance."""
        checks = []
        
        # Check for data protection headers
        if 'content-security-policy' not in security_headers:
            checks.append(ComplianceCheck(
                standard="GDPR",
                control="Data Protection Headers",
                status="non_compliant",
                evidence=["Missing Content-Security-Policy header"],
                risk_level="medium",
                remediation="Implement Content-Security-Policy header to protect against data injection"
            ))
        
        # Check for personal data in content
        personal_data_patterns = [
            r'\b\d{11}\b',  # Potential phone numbers
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email addresses
            r'\b\d{3}-\d{2}-\d{4}\b'  # SSN-like patterns
        ]
        
        found_personal_data = []
        for pattern in personal_data_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                found_personal_data.extend(matches)
        
        if found_personal_data:
            checks.append(ComplianceCheck(
                standard="GDPR",
                control="Personal Data Protection",
                status="non_compliant",
                evidence=[f"Found potential personal data: {len(found_personal_data)} instances"],
                risk_level="high",
                remediation="Remove or properly protect personal data from public content"
            ))
        
        return checks
    
    def check_iso27001_compliance(self, security_headers: Dict, ssl_config: Dict) -> List[ComplianceCheck]:
        """Check ISO 27001 compliance."""
        checks = []
        
        # Check security headers (A.13.1.1 Network security controls)
        required_headers = ['strict-transport-security', 'x-frame-options', 'x-content-type-options']
        missing_headers = [h for h in required_headers if h not in security_headers]
        
        if missing_headers:
            checks.append(ComplianceCheck(
                standard="ISO27001",
                control="A.13.1.1 Network Security Controls",
                status="partial",
                evidence=[f"Missing security headers: {', '.join(missing_headers)}"],
                risk_level="medium",
                remediation="Implement missing security headers for network protection"
            ))
        
        # Check SSL configuration (A.10.1.1 Cryptographic controls)
        if ssl_config.get('protocol_version', '') in ['SSLv2', 'SSLv3', 'TLSv1', 'TLSv1.1']:
            checks.append(ComplianceCheck(
                standard="ISO27001",
                control="A.10.1.1 Cryptographic Controls",
                status="non_compliant",
                evidence=[f"Weak SSL protocol: {ssl_config.get('protocol_version')}"],
                risk_level="high",
                remediation="Upgrade to TLS 1.2 or higher and disable weak protocols"
            ))
        
        return checks
    
    def generate_compliance_report(self, checks: List[ComplianceCheck]) -> Dict:
        """Generate comprehensive compliance report."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_checks": len(checks),
            "compliant": len([c for c in checks if c.status == "compliant"]),
            "non_compliant": len([c for c in checks if c.status == "non_compliant"]),
            "partial": len([c for c in checks if c.status == "partial"]),
            "by_standard": {},
            "high_risk_issues": [c for c in checks if c.risk_level == "high"],
            "recommendations": []
        }
        
        # Group by standard
        for check in checks:
            if check.standard not in report["by_standard"]:
                report["by_standard"][check.standard] = {
                    "total": 0,
                    "compliant": 0,
                    "non_compliant": 0,
                    "partial": 0
                }
            
            report["by_standard"][check.standard]["total"] += 1
            report["by_standard"][check.standard][check.status] += 1
        
        # Generate recommendations
        report["recommendations"] = [
            "Implement missing security headers to improve compliance",
            "Upgrade SSL/TLS configuration to meet modern standards",
            "Review and remove personal data from public content",
            "Establish regular compliance monitoring processes"
        ]
        
        return report

class EnterpriseSecurityMonitor:
    """Enterprise-grade security monitoring system."""
    
    def __init__(self, config_file: str = "enterprise_config.yaml"):
        self.config = self.load_config(config_file)
        self.anomaly_detector = AnomalyDetector(self.config.get('anomaly_detection', {}))
        self.threat_manager = ThreatIntelligenceManager(self.config.get('threat_intelligence', {}))
        self.compliance_manager = ComplianceManager(self.config.get('compliance', {}))
        self.security_events = []
        
    def load_config(self, config_file: str) -> Dict:
        """Load enterprise configuration."""
        default_config = {
            "anomaly_detection": {
                "enabled": True,
                "anomaly_threshold": 2.0,
                "window_size": 100
            },
            "threat_intelligence": {
                "enabled": True,
                "threat_feeds": {
                    "malware_domains": {
                        "enabled": True,
                        "url": "https://example.com/threat-feed"
                    }
                }
            },
            "compliance": {
                "enabled": True,
                "standards": ["GDPR", "ISO27001", "SOC2"]
            },
            "reporting": {
                "enabled": True,
                "frequency": "daily",
                "formats": ["json", "pdf", "markdown"]
            }
        }
        
        config_path = Path(config_file)
        if config_path.exists():
            with open(config_path, 'r') as f:
                user_config = yaml.safe_load(f)
                default_config.update(user_config)
        
        return default_config
    
    async def collect_metrics(self) -> List[Dict]:
        """Collect security metrics."""
        metrics = []
        
        # Collect website metrics
        try:
            async with aiohttp.ClientSession() as session:
                start_time = datetime.now()
                async with session.get('https://obywatel.bielik.ai') as response:
                    end_time = datetime.now()
                    response_time = (end_time - start_time).total_seconds() * 1000
                    
                    metrics.append({
                        "timestamp": datetime.now(),
                        "response_time": response_time,
                        "status_code": response.status,
                        "content_length": response.headers.get('content-length', 0),
                        "error_rate": 1.0 if response.status >= 400 else 0.0
                    })
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            metrics.append({
                "timestamp": datetime.now(),
                "response_time": 0,
                "status_code": 0,
                "content_length": 0,
                "error_rate": 1.0
            })
        
        return metrics
    
    async def analyze_security_headers(self) -> Dict:
        """Analyze security headers."""
        headers = {}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://obywatel.bielik.ai') as response:
                    response_headers = dict(response.headers)
                    
                    # Extract security headers
                    security_headers = [
                        'content-security-policy',
                        'x-frame-options',
                        'x-content-type-options',
                        'referrer-policy',
                        'strict-transport-security',
                        'permissions-policy'
                    ]
                    
                    for header in security_headers:
                        if header in response_headers:
                            headers[header] = response_headers[header]
        
        except Exception as e:
            logger.error(f"Failed to analyze security headers: {e}")
        
        return headers
    
    async def analyze_ssl_configuration(self) -> Dict:
        """Analyze SSL/TLS configuration."""
        ssl_config = {}
        
        try:
            import ssl
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            async with aiohttp.ClientSession() as session:
                async with session.get('https://obywatel.bielik.ai', ssl=context) as response:
                    ssl_info = response.connection.get_extra_info('ssl_object')
                    if ssl_info:
                        ssl_config = {
                            "protocol_version": ssl_info.version(),
                            "cipher_name": ssl_info.cipher()[0],
                            "cipher_bits": ssl_info.cipher()[1],
                            "compression": ssl_info.compression()
                        }
        
        except Exception as e:
            logger.error(f"Failed to analyze SSL configuration: {e}")
        
        return ssl_config
    
    async def run_enterprise_analysis(self) -> Dict:
        """Run comprehensive enterprise security analysis."""
        logger.info("Starting enterprise security analysis...")
        
        # Collect metrics
        metrics = await self.collect_metrics()
        
        # Analyze security headers
        security_headers = await self.analyze_security_headers()
        
        # Analyze SSL configuration
        ssl_config = await self.analyze_ssl_configuration()
        
        # Get website content for analysis
        content = ""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://obywatel.bielik.ai') as response:
                    content = await response.text()
        except Exception as e:
            logger.error(f"Failed to fetch content: {e}")
        
        # Anomaly detection
        anomalies = []
        if self.config['anomaly_detection']['enabled']:
            self.anomaly_detector.collect_baseline(metrics)
            anomalies = self.anomaly_detector.detect_anomalies(metrics)
        
        # Threat intelligence
        threat_events = []
        if self.config['threat_intelligence']['enabled']:
            threats = await self.threat_manager.fetch_threat_intelligence()
            threat_events = self.threat_manager.check_indicators(content, threats)
        
        # Compliance checks
        compliance_checks = []
        if self.config['compliance']['enabled']:
            if 'GDPR' in self.config['compliance']['standards']:
                compliance_checks.extend(
                    self.compliance_manager.check_gdpr_compliance(security_headers, content)
                )
            if 'ISO27001' in self.config['compliance']['standards']:
                compliance_checks.extend(
                    self.compliance_manager.check_iso27001_compliance(security_headers, ssl_config)
                )
        
        # Generate compliance report
        compliance_report = {}
        if compliance_checks:
            compliance_report = self.compliance_manager.generate_compliance_report(compliance_checks)
        
        # Compile results
        results = {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "security_headers": security_headers,
            "ssl_configuration": ssl_config,
            "anomalies": [asdict(event) for event in anomalies],
            "threat_events": [asdict(event) for event in threat_events],
            "compliance_checks": [asdict(check) for check in compliance_checks],
            "compliance_report": compliance_report,
            "summary": {
                "total_events": len(anomalies) + len(threat_events),
                "anomaly_count": len(anomalies),
                "threat_count": len(threat_events),
                "compliance_score": self._calculate_compliance_score(compliance_checks),
                "security_score": self._calculate_security_score(security_headers, ssl_config)
            }
        }
        
        # Save results
        await self._save_results(results)
        
        logger.info(f"Enterprise analysis completed. Events: {results['summary']['total_events']}")
        
        return results
    
    def _calculate_compliance_score(self, checks: List[ComplianceCheck]) -> float:
        """Calculate overall compliance score."""
        if not checks:
            return 0.0
        
        total_score = 0
        for check in checks:
            if check.status == "compliant":
                total_score += 100
            elif check.status == "partial":
                total_score += 50
            # non_compliant gets 0 points
        
        return total_score / len(checks)
    
    def _calculate_security_score(self, headers: Dict, ssl_config: Dict) -> float:
        """Calculate overall security score."""
        score = 0.0
        
        # Security headers (40 points)
        required_headers = [
            'content-security-policy',
            'x-frame-options',
            'x-content-type-options',
            'referrer-policy',
            'strict-transport-security',
            'permissions-policy'
        ]
        
        header_score = (len(headers) / len(required_headers)) * 40
        score += header_score
        
        # SSL configuration (30 points)
        if ssl_config.get('protocol_version', '') in ['TLSv1.2', 'TLSv1.3']:
            score += 20
        if ssl_config.get('cipher_bits', 0) >= 128:
            score += 10
        
        # Basic functionality (30 points)
        score += 30  # Assuming site is accessible
        
        return min(score, 100.0)
    
    async def _save_results(self, results: Dict):
        """Save analysis results."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save JSON report
        json_file = f"enterprise_analysis_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        # Save markdown report
        md_file = f"enterprise_analysis_{timestamp}.md"
        await self._generate_markdown_report(results, md_file)
        
        logger.info(f"Results saved to {json_file} and {md_file}")
    
    async def _generate_markdown_report(self, results: Dict, filename: str):
        """Generate markdown report."""
        report = f"""# Enterprise Security Analysis Report

**Generated:** {results['timestamp']}
**Target:** obywatel.bielik.ai

## Executive Summary

- **Security Score:** {results['summary']['security_score']:.1f}/100
- **Compliance Score:** {results['summary']['compliance_score']:.1f}/100
- **Total Security Events:** {results['summary']['total_events']}
- **Anomalies Detected:** {results['summary']['anomaly_count']}
- **Threat Indicators:** {results['summary']['threat_count']}

## Security Analysis

### Security Headers
{len(results['security_headers'])}/6 required headers present

"""
        
        for header, value in results['security_headers'].items():
            report += f"- **{header}:** Present\n"
        
        report += f"""
### SSL/TLS Configuration
- **Protocol:** {results['ssl_configuration'].get('protocol_version', 'Unknown')}
- **Cipher:** {results['ssl_configuration'].get('cipher_name', 'Unknown')}
- **Cipher Strength:** {results['ssl_configuration'].get('cipher_bits', 0)} bits

## Security Events

### Anomalies Detected
"""
        
        for anomaly in results['anomalies']:
            report += f"""
#### {anomaly['event_type'].replace('_', ' ').title()}
- **Severity:** {anomaly['severity']}
- **Confidence:** {anomaly['confidence']:.2f}
- **Details:** {anomaly['details']}
- **Remediation:** {anomaly.get('remediation', 'N/A')}
"""
        
        report += """
### Threat Intelligence Events
"""
        
        for threat in results['threat_events']:
            report += f"""
#### {threat['event_type'].replace('_', ' ').title()}
- **Severity:** {threat['severity']}
- **Indicator:** {threat['details'].get('indicator', 'N/A')}
- **Threat Type:** {threat['details'].get('threat_type', 'N/A')}
- **Confidence:** {threat['confidence']:.2f}
"""
        
        report += """
## Compliance Analysis

"""
        
        if results['compliance_report']:
            report += f"""
### Overall Compliance Status
- **Total Checks:** {results['compliance_report']['total_checks']}
- **Compliant:** {results['compliance_report']['compliant']}
- **Non-Compliant:** {results['compliance_report']['non_compliant']}
- **Partial:** {results['compliance_report']['partial']}

### High Risk Issues
"""
            
            for issue in results['compliance_report']['high_risk_issues']:
                report += f"""
- **{issue.standard} - {issue.control}:** {issue.status}
  - **Risk Level:** {issue.risk_level}
  - **Remediation:** {issue.remediation}
"""
        
        report += """
## Recommendations

1. **Implement Missing Security Headers**
2. **Upgrade SSL/TLS Configuration**
3. **Monitor Anomalies and Threats**
4. **Address Compliance Issues**
5. **Establish Regular Security Reviews**

---
*Report generated by Enterprise Security Monitor*
"""
        
        with open(filename, 'w') as f:
            f.write(report)

async def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enterprise Security Monitoring")
    parser.add_argument('--config', default='enterprise_config.yaml', help='Configuration file')
    parser.add_argument('--output', help='Output directory for reports')
    
    args = parser.parse_args()
    
    monitor = EnterpriseSecurityMonitor(args.config)
    
    # Run enterprise analysis
    results = await monitor.run_enterprise_analysis()
    
    # Display summary
    print("\n🔒 Enterprise Security Analysis Results")
    print("=" * 50)
    print(f"Security Score: {results['summary']['security_score']:.1f}/100")
    print(f"Compliance Score: {results['summary']['compliance_score']:.1f}/100")
    print(f"Total Events: {results['summary']['total_events']}")
    print(f"Anomalies: {results['summary']['anomaly_count']}")
    print(f"Threat Indicators: {results['summary']['threat_count']}")
    
    if results['summary']['total_events'] > 0:
        print("\n🚨 Security Events Detected:")
        for event in results['anomalies'][:3]:
            print(f"  • {event['event_type']}: {event['severity']} severity")
        for event in results['threat_events'][:3]:
            print(f"  • {event['event_type']}: {event['severity']} severity")

if __name__ == "__main__":
    asyncio.run(main())
