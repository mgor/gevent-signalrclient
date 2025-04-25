import logging
import urllib.parse as parse
from contextlib import suppress

http_schemas = ('http', 'https')
websocket_schemas = ('ws', 'wss')
http_to_ws = {k: v for k, v in zip(http_schemas, websocket_schemas)}  # noqa: C416
ws_to_http = {k: v for k, v in zip(websocket_schemas, http_schemas)}  # noqa: C416


class Helpers:
    @staticmethod
    def configure_logger(level=logging.INFO, handler=None):
        logger = Helpers.get_logger()
        if handler is None:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            handler.setLevel(level)
        logger.addHandler(handler)
        logger.setLevel(level)

    @staticmethod
    def get_logger():
        return logging.getLogger("SignalRCoreClient")

    @staticmethod
    def has_querystring(url):
        return "?" in url

    @staticmethod
    def split_querystring(url):
        parts = url.split("?")
        return parts[0], parts[1]

    @staticmethod
    def _replace_scheme(url: str, ws: bool) -> str:
        """
        Replaces the scheme of a given URL from HTTP to WebSocket or vice versa.

        Args:
            url (str): The URL whose scheme is to be replaced.
            ws (bool): If True, replace HTTP with WebSocket schemes. If False, replace WebSocket with HTTP schemes.

        Returns:
            str: The URL with the replaced scheme.
        """
        scheme, netloc, path, query, fragment = parse.urlsplit(url)

        with suppress(KeyError):
            mapping = http_to_ws if ws else ws_to_http
            scheme = mapping[scheme]

        return parse.urlunsplit((scheme, netloc, path, query, fragment))

    @staticmethod
    def replace_scheme(
            url,
            root_scheme,
            source,
            secure_source,
            destination,
            secure_destination):
        url_parts = parse.urlsplit(url)

        if root_scheme not in url_parts.scheme:
            if url_parts.scheme == secure_source:
                url_parts = url_parts._replace(scheme=secure_destination)
            if url_parts.scheme == source:
                url_parts = url_parts._replace(scheme=destination)

        return parse.urlunsplit(url_parts)

    @staticmethod
    def websocket_to_http(url):
        return Helpers.replace_scheme(
            url,
            "http",
            "ws",
            "wss",
            "http",
            "https")

    @staticmethod
    def http_to_websocket(url):
        return Helpers.replace_scheme(
            url,
            "ws",
            "http",
            "https",
            "ws",
            "wss"
        )

    @staticmethod
    def get_negotiate_url(url: str) -> str:
        """
        Constructs the negotiation URL for the given SignalR endpoint URL.

        Args:
            url (str): The base SignalR endpoint URL.

        Returns:
            str: The negotiation URL.
        """
        scheme, netloc, path, query, fragment = parse.urlsplit(url)

        path = path.rstrip('/') + '/negotiate'
        with suppress(KeyError):
            scheme = ws_to_http[scheme]

        return parse.urlunsplit((scheme, netloc, path, query, fragment))

    @staticmethod
    def encode_connection_id(url, id):
        url_parts = parse.urlsplit(url)
        query_string_parts = parse.parse_qs(url_parts.query)
        query_string_parts["id"] = id

        url_parts = url_parts._replace(
            query=parse.urlencode(
                query_string_parts,
                doseq=True))

        return Helpers.http_to_websocket(parse.urlunsplit(url_parts))
