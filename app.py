import streamlit as st
import json
import csv
from collections import defaultdict
import requests
import pandas as pd
import io

# Function to get market data from Imperator API
def fetch_market_data():
    url = "https://dydx-testnet.imperator.co/v4/perpetualMarkets?limit=100"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()["markets"]
    else:
        return {}

# Function to process the uploaded files and generate comparison tables
def process_files(json_file, csv_file):
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

    # Create a dictionary to map clob_id to subticks from clob_mid_prices
    clob_mid_prices = data.get("mev_node_to_node", {}).get("clob_mid_prices", [])
    clob_id_to_subticks = {item["clob_pair"]["id"]: item["subticks"] for item in clob_mid_prices}

    def get_market_data(clob_id, clob_id_to_market):
        str_clob_id = str(clob_id)  # Convert the clob_id to string
        if str_clob_id in clob_id_to_market:
            ticker = clob_id_to_market[str_clob_id]['ticker']
            atomicResolution = clob_id_to_market[str_clob_id]['atomicResolution']
            quantumConversionExponent = clob_id_to_market[str_clob_id]['quantumConversionExponent']
            return ticker, atomicResolution, quantumConversionExponent
        else:
            return None, None, None

    def get_subticks(clob_id, clob_id_to_subticks, atomic_resolution):
        if clob_id in clob_id_to_subticks:
            subticks = clob_id_to_subticks[clob_id]
            adjusted_subticks = subticks / (10 ** abs(atomic_resolution))
            return adjusted_subticks
        return "N/A"

    # Initialize a dictionary to store the sum of fill_amount for each taker, maker, and clob_id
    owner_fill_amounts = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    # Extract the relevant data
    matches = data.get("mev_node_to_node", {}).get("validator_mev_matches", {}).get("matches", [])

    # Iterate through each match
    for match in matches:
        taker_owner = match["taker_order_subaccount_id"]["owner"]
        maker_owner = match["maker_order_subaccount_id"]["owner"]
        clob_pair_id = match["clob_pair_id"]
        fill_amount = match["fill_amount"]

        # Sum the fill_amount for each combination of taker, maker, and clob_id
        owner_fill_amounts[taker_owner][maker_owner][clob_pair_id] += fill_amount

    clob_ids_as_strings = list(clob_id_to_market.keys())
    clob_ids_as_integers = [int(clob_id) for clob_id in clob_ids_as_strings]

    # Extract JSON data
    json_data_dict = {}

    for taker, maker_data in owner_fill_amounts.items():
        for maker, clob_data in maker_data.items():
            for clob_id, total_fill_amount in clob_data.items():
                if clob_id in clob_ids_as_integers:
                    ticker, atomicResolution, quantumConversionExponent = get_market_data(clob_id, clob_id_to_market)
                    adjusted_fill_amount = total_fill_amount / (10 ** abs(atomicResolution))
                    json_data_dict[(taker, maker, ticker)] = adjusted_fill_amount

    # Initialize dictionaries to store the sum of VOLUME and VOLUME_USD for each taker and maker
    taker_totals = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    maker_totals = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    # Extract CSV data
    csv_data_dict = {}

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

                csv_data_dict[(taker, maker, ticker)] = (adjusted_volume, adjusted_volume_usd)

    # Create CSV-based comparison table
    csv_comparison_table = []

    for (taker, maker, ticker), (volume, volume_usd) in csv_data_dict.items():
        volume_json = json_data_dict.get((taker, maker, ticker), "N/A")
        csv_comparison_table.append((taker, maker, ticker, volume, volume_usd, volume_json))

    # Create JSON-based comparison table
    json_comparison_table = []

    for (taker, maker, ticker), volume_json in json_data_dict.items():
        csv_data = csv_data_dict.get((taker, maker, ticker), ("N/A", "N/A"))
        volume, volume_usd = csv_data
        json_comparison_table.append((taker, maker, ticker, volume_json, volume, volume_usd))

    # Create the third table for validator_mev_matches
    validator_mev_matches_table = []
    for match in matches:
        taker_owner = match["taker_order_subaccount_id"]["owner"]
        maker_owner = match["maker_order_subaccount_id"]["owner"]
