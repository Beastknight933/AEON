"""Server-Side Request Forgery (SSRF) Protection and Outbound URL Validator."""

import ipaddress
import socket
from urllib.parse import urlparse
from security_hardening.core.errors import SSRFBlockedError


class SSRFGuard:
    """Validates outbound HTTP targets to block internal network access and cloud metadata leakage."""

    FORBIDDEN_IP_NETWORKS = [
        ipaddress.ip_network("0.0.0.0/8"),          # Current network
        ipaddress.ip_network("10.0.0.0/8"),         # RFC 1918 Private
        ipaddress.ip_network("127.0.0.0/8"),        # Loopback
        ipaddress.ip_network("169.254.0.0/16"),     # Link-Local (Cloud Metadata 169.254.169.254)
        ipaddress.ip_network("172.16.0.0/12"),      # RFC 1918 Private
        ipaddress.ip_network("192.168.0.0/16"),     # RFC 1918 Private
        ipaddress.ip_network("224.0.0.0/4"),        # Multicast
        ipaddress.ip_network("240.0.0.0/4"),        # Reserved
        ipaddress.ip_network("::1/128"),            # IPv6 Loopback
        ipaddress.ip_network("fc00::/7"),           # IPv6 Unique Local
        ipaddress.ip_network("fe80::/10"),          # IPv6 Link-Local
    ]

    ALLOWED_SCHEMES = {"https", "http"}

    @classmethod
    def validate_outbound_url(cls, url: str) -> None:
        """Validate destination URL against SSRF vulnerabilities.

        Raises:
            SSRFBlockedError if URL points to forbidden scheme, hostname, or private IP.
        """
        parsed = urlparse(url)

        # 1. Scheme check
        if parsed.scheme.lower() not in cls.ALLOWED_SCHEMES:
            raise SSRFBlockedError(f"Unsupported scheme '{parsed.scheme}'. Only HTTP/HTTPS permitted.")

        hostname = parsed.hostname
        if not hostname:
            raise SSRFBlockedError("Invalid URL: missing hostname.")

        # 2. Block localhost literal aliases
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "metadata.google.internal"):
            raise SSRFBlockedError(f"Access to local host '{hostname}' is blocked.")

        # 3. Resolve IP and check against forbidden CIDR ranges
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                for forbidden_net in cls.FORBIDDEN_IP_NETWORKS:
                    if ip_obj in forbidden_net:
                        raise SSRFBlockedError(
                            f"Hostname '{hostname}' resolves to private/restricted IP {ip_str}"
                        )
        except socket.gaierror as e:
            raise SSRFBlockedError(f"Failed to resolve hostname '{hostname}': {e}")

