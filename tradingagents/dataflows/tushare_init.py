import os
import tushare as ts

def init_tushare_pro():
    """
    Initialize Tushare Pro API with custom token and HTTP URL.
    This token supports historical minute data and real-time daily data.
    """
    # Use the token provided by the user
    token = 'XnZKUfOqUMVRPqLuocRfaoNmdCvOYgCEOLZfQzAFvImsXzQPSxkbNBXscYPMZssR'
    
    # ts.set_token is recommended to be called so other ts.* functions might use it if needed
    ts.set_token(token)
    
    pro = ts.pro_api(token)
    
    # Override the HTTP URL for custom data provider
    pro._DataApi__http_url = "http://124.220.22.110:8020/"
    
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
