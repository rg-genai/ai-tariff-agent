import streamlit as st
import pandas as pd
from tariff_engine import load_all_data, calculate_all_tariffs, clean_hts
import json
import google.generativeai as genai

# --- Page Configuration ---
st.set_page_config(page_title="AI Tariff Calculator", page_icon="🧮", layout="wide")

# --- Gemini API Configuration ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception as e:
    st.warning("Gemini API Key not found. Please set it in your secrets.toml file.")

# --- Data Loading & Caching ---
@st.cache_data
def cached_load_data():
    """Loads and cleans all data files, caching the result."""
    return load_all_data()

all_dataframes = cached_load_data()


# --- Function 1: Deterministic File Lookup ---
# In app.py, replace the get_hts_data_from_file function.

@st.cache_data
def get_hts_data_from_file(hts_code: str):
    """
    Performs a deterministic hierarchical lookup (10, 8, 6, then 4-digit) 
    in the Final_HTS.csv file.
    """
    if 'general' not in all_dataframes:
        return None
    general_df = all_dataframes['general']
    clean_code = clean_hts(hts_code)
    
    # --- THIS IS THE FIX ---
    # The search now starts from 10 digits, making it find the most specific match first.
    for length in [10, 8, 6, 4]:
        # We only take the first `length` characters if the code is long enough
        target_code = clean_code[:length]
        
        # Match against the cleaned HTS code column from your file
        match = general_df.loc[general_df['HTS_Code_Clean'].astype(str) == target_code]
        if not match.empty:
            st.success(f"✅ Found HTS match in database at {length}-digit level.")
            return match.iloc[0].to_dict() # Return the first found row
            
    return None # Return None if no match is found at any level

# --- Function 2: The AI Analyzer ---
@st.cache_data
def get_calculation_plan_from_gemini(rate_string: str) -> dict:
    """
    Takes a complex tariff string and uses Gemini 1.5 Flash to create a structured calculation plan.
    """
    st.info(f"🤖 Asking Gemini 1.5 Flash to analyze rate: '{rate_string}'...")
    model = genai.GenerativeModel(
        'gemini-1.5-flash-latest',
        generation_config={"response_mime_type": "application/json"}
    )
    prompt = f"""
    You are an expert customs tariff specialist. Your task is to analyze a duty rate string from the US HTS and create a JSON plan.
    Analyze this rate string: "{rate_string}"
    Here are examples:
    1. If "Free", JSON is: {{"decimal_rate": 0.0, "requires_more_info": false, "explanation": "This item is free of duty."}}
    2. If "2.5%", JSON is: {{"decimal_rate": 0.025, "requires_more_info": false, "explanation": "A simple 2.5% duty based on the value of the goods."}}
    3. If "4.4¢/kg + 6%", JSON is: {{"decimal_rate": 0.06, "requires_more_info": true, "explanation": "A compound duty: 6% of the value, PLUS a specific duty of 4.4 cents per kilogram. The calculation below only includes the 6%."}}
    4. If "1.1¢/each", JSON is: {{"decimal_rate": 0.0, "requires_more_info": true, "explanation": "A specific duty of 1.1 cents per unit. The calculation below does not include this duty."}}
    5. If "The rate applicable to the article of which the part", JSON is: {{"decimal_rate": 0.0, "requires_more_info": true, "explanation": "Duty is not specified directly and depends on the main article. Manual lookup is required."}}
    Now, create the JSON plan for the provided rate string: "{rate_string}"
    """
    try:
        response = model.generate_content(prompt)
        data = json.loads(response.text)
        st.success("✅ Calculation plan created.")
        return data
    except Exception as e:
        st.error(f"AI Analyzer failed: {e}")
        return { "decimal_rate": 0.0, "requires_more_info": True, "explanation": f"The AI could not process the rate string '{rate_string}'."}

# --- Main App Interface ---
st.title("AI Tariff Calculation Agent 🧮")
st.markdown("Enter the product's HTS code and country of import to calculate the estimated tariffs.")

# Initialize session state
if 'results' not in st.session_state:
    st.session_state['results'] = None

with st.sidebar:
    st.header("Input Parameters")
    hts_input = st.text_input("Enter HTS Code:")
    country_input = st.selectbox("Select Country of Import:", ("China", "Germany", "Canada", "Mexico", "Japan", "Other"))
    st.markdown("---")

if st.button("Calculate Tariffs"):
    if not hts_input:
        st.warning("Please enter an HTS code to proceed.")
    else:
        with st.spinner('Performing lookups and AI analysis...'):
            # Step 1: Look up data in our local file
            hts_data = get_hts_data_from_file(hts_input)
            
            if hts_data:
                # Step 2: If found, get the description and the complex rate string
                description = hts_data.get('HTS Description', 'N/A')
                rate_string = hts_data.get('General Rate of Duty', 'Free')
                
                # Display description immediately
                st.info(f"**HTS Description:** {description}")

                # Step 3: Send the complex rate string to Gemini to get a calculation plan
                plan = get_calculation_plan_from_gemini(str(rate_string))
                
                # Step 4: Use the deciphered rate from the plan in our engine
                live_general_rate = plan.get('decimal_rate', 0.0)
                
                results = calculate_all_tariffs(hts_input, country_input, all_dataframes, live_general_rate)
                
                # Save everything to session state to display below
                st.session_state['results'] = results
                st.session_state['plan'] = plan
            else:
                st.error(f"HTS Code '{hts_input}' not found in the provided data file.")
                st.session_state['results'] = None

# --- Display Results Section ---
if st.session_state.get('results'):
    results = st.session_state['results']
    plan = st.session_state.get('plan')

    # Display the AI's explanation of the duty rate
    if plan:
        st.success(f"**Rate Explanation:** {plan.get('explanation')}")
        if plan.get('requires_more_info'):
            st.warning("Please note: This tariff is complex. The calculations below only reflect the percentage-based (ad valorem) portion of the duty.")

    # The rest of the display logic remains the same
    st.subheader(f"Step 1: Tariff Percentage Summary for HTS {hts_input}")
    # ... (code for displaying tables and getting FOB values) ...
    # This entire block is copied from our last working version and needs no changes.
    display_data = []
    is_composite = list(results.values())[0].get('is_composite', False)
    for scenario_name, result_data in results.items():
        row = {"Scenario": scenario_name}
        if is_composite:
            row["Metal Component Tariff"] = f"{result_data.get('Metal Component Tariff %', 0):.2%}"
            row["Other Component Tariff"] = f"{result_data.get('Other Component Tariff %', 0):.2%}"
        else:
            row["Total Tariff"] = f"{result_data.get('Total Tariff %', 0):.2%}"
        display_data.append(row)
    st.table(pd.DataFrame(display_data).set_index("Scenario"))
    st.markdown("---")
    st.subheader("Step 2: Calculate Total Landed Cost")
    if is_composite:
        st.markdown("This product is subject to Section 232. Please provide the value breakdown.")
        col1, col2 = st.columns(2)
        metal_value = col1.number_input("Enter Metal Component Value ($):", min_value=0.0, format="%.2f", key="metal")
        other_value = col2.number_input("Enter Other Component Value ($):", min_value=0.0, format="%.2f", key="other")
        total_fob = metal_value + other_value
        if total_fob > 0:
            st.info(f"Total FOB Value: **${total_fob:,.2f}**")
    else:
        total_fob = st.number_input("Enter Total FOB Value ($):", min_value=0.0, format="%.2f", key="total")
    if total_fob > 0:
        landed_cost_data = []
        for scenario_name, result_data in results.items():
            row = {"Scenario": scenario_name}
            if is_composite:
                metal_tariff = metal_value * result_data.get('Metal Component Tariff %', 0)
                other_tariff = other_value * result_data.get('Other Component Tariff %', 0)
                total_tariff_value = metal_tariff + other_tariff
            else:
                total_tariff_value = total_fob * result_data.get('Total Tariff %', 0)
            row["Total Tariff Value"] = f"${total_tariff_value:,.2f}"
            row["Total Landed Cost"] = f"${total_fob + total_tariff_value:,.2f}"
            landed_cost_data.append(row)
        st.table(pd.DataFrame(landed_cost_data).set_index("Scenario"))
    with st.expander("Show Detailed Component Breakdown"):
        for scenario_name, result_data in results.items():
            st.subheader(f"Details for: {scenario_name}")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Component Rates:**")
                for component_name, rate in result_data.get('components', {}).items():
                    st.markdown(f"- {component_name}: **{rate:.2%}**")
            with col2:
                st.markdown("**Scenario Totals:**")
                if result_data.get('is_composite', False):
                    st.markdown(f"- Metal Tariff: **{result_data.get('Metal Component Tariff %', 0):.2%}**")
                    st.markdown(f"- Other Tariff: **{result_data.get('Other Component Tariff %', 0):.2%}**")
                else:
                    st.markdown(f"- Total Tariff: **{result_data.get('Total Tariff %', 0):.2%}**")