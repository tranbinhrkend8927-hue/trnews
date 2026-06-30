import os
import sys
import time
import pytest
from unittest import mock

# Add the current working directory to the system path
path = str(os.getcwd())
if path not in sys.path:
    sys.path.append(path)

from tradingview_scraper.symbols.markets import Markets


def mock_markets_response(columns=None):
    columns = columns or [
        'name',
        'close',
        'change',
        'change_abs',
        'volume',
        'Recommend.All',
        'market_cap_basic',
        'price_earnings_ttm',
        'earnings_per_share_basic_ttm',
        'sector',
        'industry',
    ]
    row_values = {
        'name': 'AAPL',
        'close': 150.25,
        'change': 2.5,
        'change_abs': 3.75,
        'volume': 50000000,
        'Recommend.All': 0.8,
        'market_cap_basic': 2500000000000,
        'price_earnings_ttm': 25.5,
        'earnings_per_share_basic_ttm': 6.0,
        'sector': 'Technology',
        'industry': 'Consumer Electronics',
    }

    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'data': [{'s': 'NASDAQ:AAPL', 'd': [row_values[column] for column in columns]}],
        'totalCount': 1,
    }
    return mock_response


class TestMarkets:
    @pytest.fixture
    def markets(self):
        """Fixture to create an instance of Markets for testing."""
        return Markets(export_result=False)

    def test_validate_market_valid(self, markets):
        """Test validation of valid markets."""
        try:
            markets._validate_market('america')
            markets._validate_market('crypto')
            markets._validate_market('uk')
        except ValueError:
            pytest.fail("Valid market should not raise ValueError")

    def test_validate_market_invalid(self, markets):
        """Test validation of invalid market."""
        with pytest.raises(ValueError, match="Unsupported market"):
            markets._validate_market('invalid-market')

    def test_validate_sort_by_valid(self, markets):
        """Test validation of valid sort criteria."""
        assert markets._validate_sort_by('market_cap') == 'market_cap_basic'
        assert markets._validate_sort_by('volume') == 'volume'
        assert markets._validate_sort_by('change') == 'change'

    def test_validate_sort_by_invalid(self, markets):
        """Test validation of invalid sort criteria."""
        with pytest.raises(ValueError, match="Unsupported sort criteria"):
            markets._validate_sort_by('invalid-criteria')

    def test_build_payload_basic(self, markets):
        """Test building basic payload."""
        payload = markets._build_payload()

        assert 'columns' in payload
        assert 'sort' in payload
        assert 'range' in payload
        assert payload['range'] == [0, 50]
        assert payload['sort']['sortBy'] == 'market_cap_basic'
        assert payload['sort']['sortOrder'] == 'desc'

    def test_build_payload_with_filters(self, markets):
        """Test building payload with filters."""
        filters = [
            {'left': 'type', 'operation': 'equal', 'right': 'stock'}
        ]
        payload = markets._build_payload(filters=filters)

        assert 'filter' in payload
        assert len(payload['filter']) == 1

    def test_build_payload_with_sort(self, markets):
        """Test building payload with custom sort."""
        payload = markets._build_payload(sort_by='volume', sort_order='asc')

        assert payload['sort']['sortBy'] == 'volume'
        assert payload['sort']['sortOrder'] == 'asc'

    def test_build_payload_with_limit(self, markets):
        """Test building payload with custom limit."""
        payload = markets._build_payload(limit=100)

        assert payload['range'] == [0, 100]

    @mock.patch('tradingview_scraper.symbols.markets.TradingViewHttpClient.post')
    def test_get_top_stocks_success(self, mock_post, markets):
        """Test successful retrieval of top stocks."""
        # Mock response
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {
                    's': 'NASDAQ:AAPL',
                    'd': [
                        'AAPL', 150.25, 2.5, 3.75, 50000000, 0.8, 2500000000000,
                        25.5, 6.0, 'Technology', 'Consumer Electronics'
                    ]
                },
                {
                    's': 'NASDAQ:MSFT',
                    'd': ['MSFT', 380.00, 1.8, 6.80, 30000000, 0.7, 2800000000000, 30.0, 12.5, 'Technology', 'Software']
                }
            ],
            'totalCount': 2
        }
        mock_post.return_value = mock_response

        # Get top stocks
        time.sleep(3)
        result = markets.get_top_stocks(market='america', by='market_cap', limit=10)

        # Assertions
        assert result['status'] == 'success'
        assert 'data' in result
        assert len(result['data']) == 2
        assert result['data'][0]['symbol'] == 'NASDAQ:AAPL'

    @mock.patch('tradingview_scraper.symbols.markets.TradingViewHttpClient.post')
    def test_get_top_stocks_no_data(self, mock_post, markets):
        """Test getting top stocks with no data."""
        # Mock response with no data
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [],
            'totalCount': 0
        }
        mock_post.return_value = mock_response

        # Get top stocks
        time.sleep(3)
        result = markets.get_top_stocks(market='america')

        # Assertions
        assert result['status'] == 'failed'
        assert 'error' in result

    @mock.patch('tradingview_scraper.symbols.markets.TradingViewHttpClient.post')
    def test_get_top_stocks_http_error(self, mock_post, markets):
        """Test getting top stocks with HTTP error."""
        # Mock error response
        mock_response = mock.Mock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_post.return_value = mock_response

        # Get top stocks
        time.sleep(3)
        result = markets.get_top_stocks(market='america')

        # Assertions
        assert result['status'] == 'failed'
        assert 'error' in result

    @mock.patch('tradingview_scraper.symbols.markets.TradingViewHttpClient.post')
    def test_get_top_stocks_request_exception(self, mock_post, markets):
        """Test getting top stocks with request exception."""
        # Mock exception
        mock_post.side_effect = Exception('Connection error')

        # Get top stocks
        time.sleep(3)
        result = markets.get_top_stocks(market='america')

        # Assertions
        assert result['status'] == 'failed'
        assert 'error' in result

    @pytest.mark.live_network
    def test_get_top_stocks_real_america_by_market_cap(self, markets):
        """Test getting real top stocks by market cap."""
        time.sleep(3)
        result = markets.get_top_stocks(
            market='america',
            by='market_cap',
            limit=10
        )

        # Assertions
        assert result is not None
        assert result['status'] == 'success'
        assert 'data' in result
        assert len(result['data']) >= 1

        # Check that data has expected structure
        if len(result['data']) > 0:
            first_item = result['data'][0]
            assert 'symbol' in first_item
            assert 'name' in first_item
            assert 'close' in first_item
            assert 'market_cap_basic' in first_item

    @pytest.mark.live_network
    def test_get_top_stocks_real_america_by_volume(self, markets):
        """Test getting real top stocks by volume."""
        time.sleep(3)
        result = markets.get_top_stocks(
            market='america',
            by='volume',
            limit=10
        )

        # Assertions
        assert result is not None
        assert result['status'] == 'success'
        assert 'data' in result
        assert len(result['data']) >= 1

    @pytest.mark.live_network
    def test_get_top_stocks_real_crypto(self, markets):
        """Test getting real top crypto."""
        time.sleep(3)
        # Note: crypto market may not return results with stock filters
        # This test just checks that the function doesn't crash
        result = markets.get_top_stocks(
            market='crypto',
            by='volume',
            limit=10
        )

        # Assertions - we accept both success and failed for crypto
        # since the stock filter may not match crypto instruments
        assert result is not None
        assert 'status' in result

    @mock.patch('tradingview_scraper.symbols.markets.TradingViewHttpClient.post')
    def test_get_top_stocks_with_custom_columns(self, mock_post, markets):
        """Test getting top stocks with custom columns."""
        time.sleep(3)
        custom_columns = ['name', 'close', 'volume', 'market_cap_basic']
        mock_post.return_value = mock_markets_response(columns=custom_columns)
        result = markets.get_top_stocks(
            market='america',
            by='market_cap',
            columns=custom_columns,
            limit=5
        )

        # Assertions
        assert result is not None
        assert result['status'] == 'success'
        if len(result['data']) > 0:
            first_item = result['data'][0]
            assert 'name' in first_item
            assert 'close' in first_item
            assert 'volume' in first_item
            assert 'market_cap_basic' in first_item

    def test_supported_markets(self, markets):
        """Test that all supported markets are accessible."""
        supported_markets = ['america', 'australia', 'canada', 'germany', 'india', 'uk', 'crypto', 'forex', 'global']

        for market in supported_markets:
            assert market in markets.SCANNER_ENDPOINTS
            assert markets.SCANNER_ENDPOINTS[market].startswith('https://')

    def test_sort_criteria(self, markets):
        """Test that sort criteria are defined."""
        assert len(markets.SORT_CRITERIA) > 0
        assert 'market_cap' in markets.SORT_CRITERIA
        assert 'volume' in markets.SORT_CRITERIA
        assert 'change' in markets.SORT_CRITERIA
