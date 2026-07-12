from portfolio_analytics import normalize_asset_id


def test_normalize_asset_id_prefers_isin():
    assert normalize_asset_id(" ie00b4l5y983 ", "MSCI World") == "IE00B4L5Y983"
    assert normalize_asset_id(None, "MSCI World") == "msci world"
