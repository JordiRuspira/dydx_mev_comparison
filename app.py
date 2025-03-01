import streamlit as st
import json
import csv
import requests
import pandas as pd
import io

# Function to get market data from Imperator API
def fetch_market_data():
    url = "https://dydx-testnet.imperator.co/v4/perpetualMarkets?limit=100"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()["markets"]
        else:
            st.error("Failed to fetch market data from the API.")
            return {}
    except Exception as e:
        st.error(f"An error occurred while fetching market data: {e}")
        return {}

# Function to process the uploaded files and generate comparison tables
def process_files(json_file, csv_file=None):
    try:
        # Load the JSON data
        data = json.load(json_file)

        # Fetch market data
        market_data = fetch_market_data()

        # Create a dictionary to map clobPairId to market information
        clob_id_to_market = {}
        for ticker, market_info in market_data.items():
            clob_id = market_info["clobPairId"]
            clob_id_to_market[clob_id] = {
                "ticker": ticker,
                "atomicResolution": market_info["atomicResolution"],
                "quantumConversionExponent": market_info["quantumConversionExponent"],
            }

        def get_market_data(clob_id, clob_id_to_market):
            str_clob_id = str(clob_id)  # Convert the clob_id to string
            if str_clob_id in clob_id_to_market:
                ticker = clob_id_to_market[str_clob_id]['ticker']
                atomicResolution = clob_id_to_market[str_clob_id]['atomicResolution']
                quantumConversionExponent = clob_id_to_market[str_clob_id]['quantumConversionExponent']
                return ticker, atomicResolution, quantumConversionExponent
            else:
                # Handle cases where clob_id is missing or invalid
                return "Unknown", 0, 0

        clob_ids_as_strings = list(clob_id_to_market.keys())
        clob_ids_as_integers = [int(clob_id) for clob_ids_as_strings in clob_ids_as_strings]

        # Extract JSON data
        json_data_dict = {}

        matches = data.get("mev_node_to_node", {}).get("validator_mev_matches", {}).get("matches", [])
        for match in matches:
            taker_owner = match["taker_order_subaccount_id"]["owner"]
            maker_owner = match["maker_order_subaccount_id"]["owner"]
            clob_pair_id = match.get("clob_pair_id", 0)  # Default to 0 if missing
            fill_amount = match["fill_amount"]

            if clob_pair_id in clob_ids_as_integers:
                ticker, atomicResolution, quantumConversionExponent = get_market_data(clob_pair_id, clob_id_to_market)
                adjusted_fill_amount = fill_amount / (10 ** abs(atomicResolution))
                json_data_dict[(taker_owner, maker_owner, ticker)] = adjusted_fill_amount

        # Extract CSV data
        csv_comparison_table = []

        if csv_file:
            # Convert the uploaded CSV file to a file-like object
            csv_file = io.StringIO(csv_file.getvalue().decode("utf-8"))
            reader = csv.DictReader(csv_file)

            for row in reader:
                taker = row["taker"]
                maker = row["maker"]
                clob_id = row["PERPETUAL_ID"]
                volume = float(row["NON_ADJUSTED_VOLUME"])
                volume_usd_unadjusted = float(row["VOLUME_USD_UNADJUSTED"])
                price_unadjusted = float(row["NON_ADJUSTED_PRICE"])

                if clob_id in clob_ids_as_strings:
                    ticker, atomicResolution, quantumConversionExponent = get_market_data(clob_id, clob_id_to_market)
                    if ticker and atomicResolution is not None:
                        adjusted_volume = volume / (10 ** abs(atomicResolution))
                        price_adjusted = price_unadjusted * (10 ** (-6 + abs(atomicResolution)))
                        adjusted_volume_usd = adjusted_volume * price_adjusted
                        csv_comparison_table.append((taker, maker, ticker, adjusted_volume, adjusted_volume_usd))

        # Validator MEV Matches table
        validator_mev_table = []

        clob_mid_prices = data.get("mev_node_to_node", {}).get("clob_mid_prices", [])

        for match in matches:
            taker_owner = match["taker_order_subaccount_id"]["owner"]
            maker_owner = match["maker_order_subaccount_id"]["owner"]
            clob_pair_id = match.get("clob_pair_id", 0)  # Default to 0 if missing
            fill_amount = match["fill_amount"]
            ticker, atomicResolution, quantumConversionExponent = get_market_data(clob_pair_id, clob_id_to_market)
            adjusted_fill_amount = fill_amount / (10 ** abs(atomicResolution))
            maker_order_subticks = match.get("maker_order_subticks", 0)
            price_usd = maker_order_subticks / (10 ** (15 - abs(atomicResolution)))
            volume_usd = price_usd * adjusted_fill_amount
            validator_mev_table.append((taker_owner, maker_owner, ticker, adjusted_fill_amount, price_usd, volume_usd))

        # BP MEV Matches table
        bp_mev_matches = data.get("mev_node_to_node", {}).get("bp_mev_matches", {}).get("matches", [])
        bp_mev_table = []

        for match in bp_mev_matches:
            taker_owner = match["taker_order_subaccount_id"]["owner"]
            maker_owner = match["maker_order_subaccount_id"]["owner"]
            clob_pair_id = match.get("clob_pair_id", 0)  # Default to 0 if missing
            fill_amount = match["fill_amount"]
            ticker, atomicResolution, quantumConversionExponent = get_market_data(clob_pair_id, clob_id_to_market)
            adjusted_fill_amount = fill_amount / (10 ** abs(atomicResolution))
            maker_order_subticks = match.get("maker_order_subticks", 0)
            price_usd = maker_order_subticks / (10 ** (15 - abs(atomicResolution)))
            volume_usd = price_usd * adjusted_fill_amount
            bp_mev_table.append((taker_owner, maker_owner, ticker, adjusted_fill_amount, price_usd, volume_usd))

        # Liquidation Matches table for Node-to-Node and BP
        node_liquidation_mev_table = []
        bp_liquidation_mev_table = []

        # Extract liquidation matches for node-to-node
        node_liquidation_matches = data.get("mev_node_to_node", {}).get("validator_mev_matches", {}).get("liquidation_matches", [])
        for match in node_liquidation_matches:
            taker_owner = match["liquidated_subaccount_id"]["owner"]
            maker_owner = match["maker_order_subaccount_id"]["owner"]
            clob_pair_id = match.get("clob_pair_id", 0)
            fill_amount = match["fill_amount"]
            ticker, atomicResolution, quantumConversionExponent = get_market_data(clob_pair_id, clob_id_to_market)
            adjusted_fill_amount = fill_amount / (10 ** abs(atomicResolution))
            maker_order_subticks = match.get("maker_order_subticks", 0)
            price_usd = maker_order_subticks / (10 ** (15 - abs(atomicResolution)))
            volume_usd = price_usd * adjusted_fill_amount
            node_liquidation_mev_table.append((taker_owner, maker_owner, ticker, adjusted_fill_amount, price_usd, volume_usd))

        # Extract liquidation matches for BP
        bp_liquidation_matches = data.get("mev_node_to_node", {}).get("bp_mev_matches", {}).get("liquidation_matches", [])
        for match in bp_liquidation_matches:
            taker_owner = match["liquidated_subaccount_id"]["owner"]
            maker_owner = match["maker_order_subaccount_id"]["owner"]
            clob_pair_id = match.get("clob_pair_id", 0)
            fill_amount = match["fill_amount"]
            ticker, atomicResolution, quantumConversionExponent = get_market_data(clob_pair_id, clob_id_to_market)
            adjusted_fill_amount = fill_amount / (10 ** abs(atomicResolution))
            maker_order_subticks = match.get("maker_order_subticks", 0)
            price_usd = maker_order_subticks / (10 ** (15 - abs(atomicResolution)))
            volume_usd = price_usd * adjusted_fill_amount
            bp_liquidation_mev_table.append((taker_owner, maker_owner, ticker, adjusted_fill_amount, price_usd, volume_usd))

        # Calculate Total MEV value
        # Process JSON data
        mev_values = data.get("mev_datapoint", {}).get("mev", {}) 

        # Convert MEV values to floats, then sum and calculate total MEV
        mev_values_float = [float(value) for value in mev_values.values()]
        total_mev_value = sum(mev_values_float) / 10**6 

        return csv_comparison_table, validator_mev_table, bp_mev_table, node_liquidation_mev_table, bp_liquidation_mev_table, total_mev_value
    except Exception as e:
        st.error(f"An error occurred while processing the files: {e}")
        return None, None, None, None, None, 0

# Streamlit app main function
def main():
    st.title("Market Data Comparison App")

    # File upload widgets
    json_file = st.file_uploader("Upload JSON File", type=["json"])
    csv_file = st.file_uploader("Upload CSV File", type=["csv"])

    if json_file:
        # Process the uploaded files and generate comparison tables
        csv_comparison_table, validator_mev_table, bp_mev_table, node_liquidation_mev_table, bp_liquidation_mev_table, total_mev_value = process_files(json_file, csv_file)

        # Display CSV-based comparison table
        if csv_file:
            st.header("CSV-based Comparison Table")
            if csv_comparison_table:
                csv_df = pd.DataFrame(csv_comparison_table, columns=["Taker", "Maker", "Ticker", "Volume (CSV)", "Volume USD (CSV)"])
                # Convert columns to numeric types
                csv_df["Volume (CSV)"] = pd.to_numeric(csv_df["Volume (CSV)"], errors='coerce')
                csv_df["Volume USD (CSV)"] = pd.to_numeric(csv_df["Volume USD (CSV)"], errors='coerce')
                # Add Price (USD) column
                csv_df["Price (USD)"] = csv_df["Volume USD (CSV)"] / csv_df["Volume (CSV)"]
                # Sort by Volume (CSV)
                csv_df_sorted = csv_df.sort_values(by="Volume (CSV)", ascending=False)
                # Format display columns
                csv_df_display = csv_df_sorted.copy()
                csv_df_display["Volume USD (CSV)"] = csv_df_sorted["Volume USD (CSV)"].apply(lambda x: f"${x:,.2f}")
                csv_df_display["Price (USD)"] = csv_df_sorted["Price (USD)"].apply(lambda x: f"${x:,.2f}")
                st.dataframe(csv_df_display)

        # Display Validator MEV Matches table
        st.header("Validator MEV Matches Table")
        if validator_mev_table:
            validator_mev_df = pd.DataFrame(validator_mev_table, columns=["Taker", "Maker", "Ticker", "Adjusted Fill Amount", "Price (USD)", "Volume (USD)"])
            # Convert columns to numeric types
            validator_mev_df["Adjusted Fill Amount"] = pd.to_numeric(validator_mev_df["Adjusted Fill Amount"], errors='coerce')
            validator_mev_df["Price (USD)"] = pd.to_numeric(validator_mev_df["Price (USD)"], errors='coerce')
            validator_mev_df["Volume (USD)"] = pd.to_numeric(validator_mev_df["Volume (USD)"], errors='coerce')
            # Sort by Volume (USD)
            validator_mev_df_sorted = validator_mev_df.sort_values(by="Volume (USD)", ascending=False)
            # Format display columns
            validator_mev_df_display = validator_mev_df_sorted.copy()
            validator_mev_df_display["Price (USD)"] = validator_mev_df_sorted["Price (USD)"].apply(lambda x: f"${x:,.8f}")
            validator_mev_df_display["Volume (USD)"] = validator_mev_df_sorted["Volume (USD)"].apply(lambda x: f"${x:,.2f}")
            st.dataframe(validator_mev_df_display)

        # Display BP MEV Matches table
        st.header("BP MEV Matches Table")
        if bp_mev_table:
            bp_mev_df = pd.DataFrame(bp_mev_table, columns=["Taker", "Maker", "Ticker", "Adjusted Fill Amount", "Price (USD)", "Volume (USD)"])
            # Convert columns to numeric types
            bp_mev_df["Adjusted Fill Amount"] = pd.to_numeric(bp_mev_df["Adjusted Fill Amount"], errors='coerce')
            bp_mev_df["Price (USD)"] = pd.to_numeric(bp_mev_df["Price (USD)"], errors='coerce')
            bp_mev_df["Volume (USD)"] = pd.to_numeric(bp_mev_df["Volume (USD)"], errors='coerce')
            # Sort by Volume (USD)
            bp_mev_df_sorted = bp_mev_df.sort_values(by="Volume (USD)", ascending=False)
            # Format display columns
            bp_mev_df_display = bp_mev_df_sorted.copy()
            bp_mev_df_display["Price (USD)"] = bp_mev_df_sorted["Price (USD)"].apply(lambda x: f"${x:,.8f}")
            bp_mev_df_display["Volume (USD)"] = bp_mev_df_sorted["Volume (USD)"].apply(lambda x: f"${x:,.2f}")
            st.dataframe(bp_mev_df_display)

        # Display Liquidation Matches table for Node-to-Node
        st.header("Node-to-Node Liquidation Matches Table")
        if node_liquidation_mev_table:
            node_liquidation_mev_df = pd.DataFrame(node_liquidation_mev_table, columns=["Taker", "Maker", "Ticker", "Adjusted Fill Amount", "Price (USD)", "Volume (USD)"])
            # Convert columns to numeric types
            node_liquidation_mev_df["Adjusted Fill Amount"] = pd.to_numeric(node_liquidation_mev_df["Adjusted Fill Amount"], errors='coerce')
            node_liquidation_mev_df["Price (USD)"] = pd.to_numeric(node_liquidation_mev_df["Price (USD)"], errors='coerce')
            node_liquidation_mev_df["Volume (USD)"] = pd.to_numeric(node_liquidation_mev_df["Volume (USD)"], errors='coerce')
            # Sort by Volume (USD)
            node_liquidation_mev_df_sorted = node_liquidation_mev_df.sort_values(by="Volume (USD)", ascending=False)
            # Format display columns
            node_liquidation_mev_df_display = node_liquidation_mev_df_sorted.copy()
            node_liquidation_mev_df_display["Price (USD)"] = node_liquidation_mev_df_sorted["Price (USD)"].apply(lambda x: f"${x:,.8f}")
            node_liquidation_mev_df_display["Volume (USD)"] = node_liquidation_mev_df_sorted["Volume (USD)"].apply(lambda x: f"${x:,.2f}")
            st.dataframe(node_liquidation_mev_df_display)

        # Display Liquidation Matches table for BP
        st.header("BP Liquidation Matches Table")
        if bp_liquidation_mev_table:
            bp_liquidation_mev_df = pd.DataFrame(bp_liquidation_mev_table, columns=["Taker", "Maker", "Ticker", "Adjusted Fill Amount", "Price (USD)", "Volume (USD)"])
            # Convert columns to numeric types
            bp_liquidation_mev_df["Adjusted Fill Amount"] = pd.to_numeric(bp_liquidation_mev_df["Adjusted Fill Amount"], errors='coerce')
            bp_liquidation_mev_df["Price (USD)"] = pd.to_numeric(bp_liquidation_mev_df["Price (USD)"], errors='coerce')
            bp_liquidation_mev_df["Volume (USD)"] = pd.to_numeric(bp_liquidation_mev_df["Volume (USD)"], errors='coerce')
            # Sort by Volume (USD)
            bp_liquidation_mev_df_sorted = bp_liquidation_mev_df.sort_values(by="Volume (USD)", ascending=False)
            # Format display columns
            bp_liquidation_mev_df_display = bp_liquidation_mev_df_sorted.copy()
            bp_liquidation_mev_df_display["Price (USD)"] = bp_liquidation_mev_df_sorted["Price (USD)"].apply(lambda x: f"${x:,.8f}")
            bp_liquidation_mev_df_display["Volume (USD)"] = bp_liquidation_mev_df_sorted["Volume (USD)"].apply(lambda x: f"${x:,.2f}")
            st.dataframe(bp_liquidation_mev_df_display)

        # Display Total MEV value
        st.header("Total MEV Value")
        st.write(f"Total MEV value: ${total_mev_value} USD")



# Run the Streamlit app
if __name__ == "__main__":
    main()
