import hashlib
import hmac
import requests
from urllib.parse import quote
from . import config

class TOOL(object):
    def __init__(self):
        self.mexc_key = config.api_key
        self.mexc_secret = config.secret_key
        self.hosts = config.mexc_host

    def _get_server_time(self):
        url = '{}{}'.format(self.hosts, '/api/v3/time')
        return requests.request('get', url).json()['serverTime']

    def _sign_v3(self, req_time, sign_params=None, body_params=None):
        """
        Generate signature for mixed parameters (query string + body)
        sign_params: query string parameters
        body_params: request body parameters
        """
        signature_builder = []
        
        # Add query string parameters (URL encoded)
        if sign_params:
            for key, value in sign_params.items():
                signature_builder.append(f"{key}={quote(str(value))}")
        
        # Add body parameters (URL encoded) including timestamp
        if body_params:
            body_params_with_timestamp = body_params.copy()
            body_params_with_timestamp['timestamp'] = req_time
            
            for key, value in body_params_with_timestamp.items():
                signature_builder.append(f"{key}={quote(str(value))}")
        else:
            signature_builder.append(f"timestamp={req_time}")
        
        to_sign = "&".join(signature_builder)
        sign = hmac.new(self.mexc_secret.encode('utf-8'), to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        return sign

    def public_request(self, method, url, params=None):
        url = '{}{}'.format(self.hosts, url)
        return requests.request(method, url, params=params)

    def sign_request(self, method, url, params=None):
        url = '{}{}'.format(self.hosts, url)
        req_time = self._get_server_time()
        if params:
            # Create a copy to avoid mutating user params unexpectedly
            params = params.copy()
            params['signature'] = self._sign_v3(req_time=req_time, sign_params=params)
        else:
            params = {'signature': self._sign_v3(req_time=req_time)}
        params['timestamp'] = req_time
        headers = {
            'x-mexc-apikey': self.mexc_key,
            'Content-Type': 'application/json',
        }
        return requests.request(method, url, params=params, headers=headers)


class mexc_market(TOOL):
    def __init__(self):
        super().__init__()
        self.api = '/api/v3'
        self.method = 'GET'

    def get_ping(self):
        """Ping
        Test connectivity to the Rest API.
        GET /api/v3/ping
        """
        url = '{}{}'.format(self.api, '/ping')
        response = self.public_request(self.method, url)
        return response.json()

    def get_timestamp(self):
        """Check Server Time
        GET /api/v3/time
        """
        url = '{}{}'.format(self.api, '/time')
        response = self.public_request(self.method, url)
        return response.json()

    def get_exchangeInfo(self, params=None):
        """Exchange Information
        GET /api/v3/exchangeInfo
        """
        url = '{}{}'.format(self.api, '/exchangeInfo')
        response = self.public_request(self.method, url, params=params)
        return response.json()

    def get_depth(self, params):
        """Order Book
        GET /api/v3/depth
        """
        url = '{}{}'.format(self.api, '/depth')
        response = self.public_request(self.method, url, params=params)
        return response.json()

    def get_avgprice(self, params):
        """Current Average Price
        GET /api/v3/avgPrice
        https://mexcdevelop.github.io/apidocs/spot_v3_en/#current-average-price
        params:
            symbol (str): the trading pair
        """
        url = '{}{}'.format(self.api, '/avgPrice')
        response = self.sign_request(self.method, url, params=params)
        return response.json()
