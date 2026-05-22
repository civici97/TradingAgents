import os
import tushare as ts
from dotenv import load_dotenv

def init_tushare_pro():
    """
    Initialize Tushare Pro API with custom token and HTTP URL.
    This token supports historical minute data and real-time daily data.
    """
    load_dotenv()
    
    # Use the token provided by the user from env
    token = os.getenv("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set in environment or .env file.")
    
    # ts.set_token is recommended to be called so other ts.* functions might use it if needed
    ts.set_token(token)
    
    pro = ts.pro_api(token)
    
    # Override the HTTP URL for custom data provider
    custom_url = os.getenv("TUSHARE_HTTP_URL")
    if custom_url:
        pro._DataApi__http_url = custom_url
    
    return pro

if __name__ == "__main__":
    # Test as requested
    pro = init_tushare_pro()
    print("Testing index_basic...")
    df = pro.index_basic(limit=5)
    print(df)
    
    print("\nTesting pro_bar...")
    df_bar = ts.pro_bar(api=pro, ts_code="000001.SZ", limit=3)
    print(df_bar)
