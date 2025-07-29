import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

API_KEY = '0c4ef6ee25e94f3db32ffac1ce175e8f'

@st.cache_data
def load_fips_data():
    url = "https://www2.census.gov/geo/docs/reference/codes/files/national_county.txt"
    col_names = ["state_abbr", "state_fips", "county_fips", "county_name", "class_code"]
    df = pd.read_csv(url, names=col_names, dtype=str)
    df["state"] = df["state_abbr"]
    df["county"] = df["county_name"] + " County"
    df = df[["state", "county", "state_fips", "county_fips"]]
    return df

def get_series_id(state_fips, county_fips):
    return f"LAUCN{state_fips}{county_fips}0000000003"

def fetch_bls_data(series_id, start_year, end_year):
    payload = {
        "seriesid": [series_id],
        "startyear": start_year,
        "endyear": end_year,
        "registrationkey": API_KEY
    }
    response = requests.post("https://api.bls.gov/publicAPI/v2/timeseries/data/", json=payload)
    if response.status_code == 200:
        return response.json()['Results']['series'][0]['data']
    return None

def process_data(raw_data):
    df = pd.DataFrame(raw_data)
    df = df[df['value'] != '']
    df['value'] = df['value'].astype(float)
    df['year'] = df['year'].astype(int)
    df = df[df['period'].str.startswith('M')]
    df = df[df['period'] != 'M13']
    df['month_num'] = df['period'].str.extract(r'M(\d+)').astype(int)
    df['date'] = pd.to_datetime(df['year'].astype(str) + '-' + df['month_num'].astype(str) + '-01')
    return df[['date', 'year', 'month_num', 'value']]

def main():
    st.title("\U0001F4CA County vs US Unemployment")

    fips_df = load_fips_data()

    st.markdown("#### Select the state and county (as listed on the BLS website):")
    state = st.selectbox("State", sorted(fips_df['state'].unique()))
    county = st.selectbox("County", sorted(fips_df[fips_df['state'] == state]['county'].unique()))

    today = datetime.today()
    curr_year = st.number_input("Current Year", min_value=2018, max_value=today.year, value=today.year)
    curr_month = st.selectbox("Current Month", options=list(range(1, 13)), index=today.month - 1,
                              format_func=lambda x: datetime(1900, x, 1).strftime('%B'))

    selected_row = fips_df[(fips_df['state'] == state) & (fips_df['county'] == county)]

    if not selected_row.empty:
        state_fips = selected_row.iloc[0]['state_fips']
        county_fips = selected_row.iloc[0]['county_fips']
        label = f"{county}, {state}"

        if st.button("Run Comparison"):
            county_series = get_series_id(state_fips, county_fips)
            us_series = "LNS14000000"

            county_data = fetch_bls_data(county_series, "2018", str(curr_year))
            us_data = fetch_bls_data(us_series, "2018", str(curr_year))

            if not county_data or not us_data:
                st.error("\u274C Failed to fetch data. Check your FIPS codes or API key.")
                return

            df_county = process_data(county_data).rename(columns={"value": "value_county"})
            df_us = process_data(us_data).rename(columns={"value": "value_us"})

            merged = pd.merge(df_county, df_us, on="date", how="inner")
            merged['year'] = merged['date'].dt.year
            merged['delta'] = merged['value_county'] - merged['value_us']

            annual = (
                merged[(merged['year'] >= 2018) & (merged['year'] <= curr_year)]
                .groupby('year')[['value_county', 'value_us']]
                .mean()
                .reset_index()
            )
            annual['delta'] = annual['value_county'] - annual['value_us']
            annual['year'] = annual['year'].astype(int)

            st.subheader(f"\U0001F4C5 Annual Unemployment Averages (2018–{curr_year})")
            st.dataframe(
                annual.rename(columns={
                    'value_county': label,
                    'value_us': 'US Average',
                    'delta': 'Difference (County - US)'
                }),
                use_container_width=True
            )

            recent_cutoff = datetime(curr_year, curr_month, 1)
            recent = merged[merged['date'] < recent_cutoff].sort_values(by="date", ascending=False).head(6)
            recent['month_str'] = recent['date'].dt.strftime('%B %Y')

            st.subheader("\U0001F4C6 Most Recent 6 Months (Monthly Data)")
            st.dataframe(
                recent[['month_str', 'value_county', 'value_us', 'delta']].rename(columns={
                    'month_str': 'Date',
                    'value_county': label,
                    'value_us': 'US Average',
                    'delta': 'Difference (County - US)'
                }),
                use_container_width=True
            )

            last_3_months = recent.head(3)
            past_3_years = list(range(curr_year - 3, curr_year))
            annual_subset = annual[annual['year'].isin(past_3_years)]

            recent_qualifies = all(last_3_months['value_county'] > last_3_months['value_us'])
            annual_qualifies = all(annual_subset['value_county'] > annual_subset['value_us'])

            if recent_qualifies and annual_qualifies:
                st.success("\u2705 This county meets unemployment criteria for Energy Community designation.")
            else:
                st.warning("\u26A0\uFE0F This county does NOT meet unemployment criteria for Energy Community designation.")

if __name__ == "__main__":
    main()
