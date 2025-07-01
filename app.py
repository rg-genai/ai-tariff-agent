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

# ==============================================================================
# Core Application Functions
# ==============================================================================

@st.cache_data
def get_hts_data_from_file(hts_code: str):
    """
    Performs a deterministic hierarchical lookup (10, 8, 6, then 4-digit) 
    in the Final_HTS.csv file.
    """
    if 'general' not in all_dataframes:
        st.error("General HTS data file ('Final_HTS.csv') could not be loaded. Please check the file.")
        return None
        
    general_df = all_dataframes['general']
    clean_code = clean_hts(hts_code)
    for length in [10, 8, 6, 4]:
        target_code = clean_code[:length]
        match = general_df.loc[general_df['HTS_Code_Clean'].astype(str) == target_code]
        if not match.empty:
            return match.iloc[0].to_dict()
    return None

@st.cache_data
def get_calculation_plan_from_gemini(rate_string: str) -> dict:
    """
    Takes a complex tariff string and uses Gemini 2.0 Flash to create a structured calculation plan.
    """
    st.info(f"🤖 Asking Gemini 2.0 Flash to analyze rate: '{rate_string}'...")
    model = genai.GenerativeModel('gemini-2.0-flash-001', generation_config={"response_mime_type": "application/json"})
    prompt = f"""
    You are an expert customs tariff specialist. Your task is to analyze a duty rate string from the US HTS and create a JSON plan.
    Analyze this rate string: "{rate_string}"
    Your primary goal is to extract the ad valorem (percentage) part of the duty.
    Here are examples:
    1. If "Free", JSON is: {{"decimal_rate": 0.0, "requires_more_info": false, "explanation": "This item is free of duty."}}
    2. If "2.5%", JSON is: {{"decimal_rate": 0.025, "requires_more_info": false, "explanation": "A simple 2.5% duty based on the value of the goods."}}
    3. If "4.4¢/kg + 6%", JSON is: {{"decimal_rate": 0.06, "requires_more_info": true, "explanation": "A compound duty: 6% of the value, PLUS a specific duty. The calculation below only includes the 6%."}}
    4. If "1.1¢/each", JSON is: {{"decimal_rate": 0.0, "requires_more_info": true, "explanation": "A specific duty of 1.1 cents per unit. The calculation below does not include this duty."}}
    Now, create the JSON plan for the provided rate string: "{rate_string}"
    """
    try:
        response = model.generate_content(prompt)
        data = json.loads(response.text)
        st.success("✅ AI analysis complete.")
        return data
    except Exception as e:
        st.error(f"AI Analyzer failed: {e}")
        return {"decimal_rate": 0.0, "requires_more_info": True, "explanation": f"The AI could not process the rate string '{rate_string}'."}

def process_bulk_upload(df):
    """
    Processes an entire DataFrame and generates a highly detailed output DataFrame,
    using a simplified total tariff logic.
    """
    st.info(f"Starting to process {len(df)} rows...")
    progress_bar = st.progress(0, text="Processing...")
    
    results_list = []
    total_rows = len(df)
    
    for index, row in df.iterrows():
        hts_code = str(row['HTS_Code'])
        country = row['Country of Import']
        fob_value = float(row['FOB Value'])
        
        # Perform Lookups and Calculations
        hts_data = get_hts_data_from_file(hts_code)
        
        output_row = {'HTS_Code': hts_code, 'FOB_Value': fob_value, 'Country': country}
        
        if hts_data:
            description = hts_data.get('HTS Description', 'N/A')
            rate_string = hts_data.get('General Rate of Duty', 'Free')
            plan = get_calculation_plan_from_gemini(str(rate_string))
            live_general_rate = plan.get('decimal_rate', 0.0)
            
            output_row['HTS_Description'] = description
            
            tariff_results = calculate_all_tariffs(hts_code, country, all_dataframes, live_general_rate)
            
            for scenario_name, result_data in tariff_results.items():
                prefix = scenario_name.replace(" ", "_").replace("-", "")
                components = result_data.get('components', {})

                # Add all individual component percentages, formatted as strings
                for comp_name, comp_rate in components.items():
                    col_name = f"{prefix}_{comp_name.replace(' ', '_')}_%"
                    output_row[col_name] = f"{comp_rate:.2%}"

                # Add Total Tariff %, Value, and Cost using the simplified logic
                total_tariff_percent = result_data.get('Total Tariff %', 0)
                tariff_value = fob_value * total_tariff_percent
                total_cost = fob_value + tariff_value
                
                output_row[f'{prefix}_Total_Tariff_%'] = f"{total_tariff_percent:.2%}"
                output_row[f'{prefix}_Tariff_Value'] = round(tariff_value, 2)
                output_row[f'{prefix}_Total_Cost'] = round(total_cost, 2)

            results_list.append(output_row)
        else:
            output_row['HTS_Description'] = 'HTS Code Not Found in Database'
            results_list.append(output_row)

        progress_bar.progress((index + 1) / total_rows, text=f"Processing row {index + 1}/{total_rows}")

    progress_bar.empty()
    st.success(f"Processing complete for {len(results_list)} rows.")
    return pd.DataFrame(results_list)

# ==============================================================================
# Main App User Interface
# ==============================================================================
st.title("AI Tariff Calculation Agent 🧮")
st.markdown("### A tool for detailed tariff analysis and bulk processing.")

# --- NEW: Add the disclaimer above the tabs ---
st.warning(
    "**Disclaimer:** The calculated values are based on the provided data files and are for informational "
    "purposes only. Tariff rates are subject to change. Always consult with a qualified customs broker "
    "or trade lawyer for definitive guidance."
)

# --- List of all 57 countries for the dropdown ---
country_list = [
    "Algeria", "Angola", "Bangladesh", "Bosnia and Herzegovina", "Botswana", 
    "Brunei", "Cambodia", "Cameroon", "Chad", "China", "Cote d` Ivoire", 
    "Democratic Republic of Congo", "Equatorial Guinea", "European Union", 
    "Falkland Islands", "Fiji", "Guyana", "India", "Indonesia", "Iraq", "Israel", 
    "Japan", "Jordan", "Kazakhstan", "Laos", "Lesotho", "Libya", "Liechtenstein", 
    "Madagascar", "Malawi", "Malaysia", "Mauritius", "Moldova", "Mozambique", 
    "Myanmar (Burma)", "Namibia", "Nauru", "Nicaragua", "Nigeria", "North Macedonia", 
    "Norway", "Pakistan", "Philippines", "Serbia", "South Africa", "South Korea", 
    "Sri Lanka", "Switzerland", "Syria", "Taiwan", "Thailand", "Tunisia", 
    "Vanuatu", "Venezuela", "Vietnam", "Zambia", "Zimbabwe"
]

# --- Create Tabs ---
tab1, tab2 = st.tabs(["**Single Product Tariff**", "**Multi Product Tariff**"])

# --- Tab 1: Single Product Tariff ---
with tab1:
    st.header("Calculate for a Single HTS Code")
    
    if 'single_results' not in st.session_state:
        st.session_state['single_results'] = None

    col1, col2 = st.columns(2)
    with col1:
        hts_input_single = st.text_input("Enter HTS Code", key="hts_single")
    with col2:
        # --- THIS IS THE FIX ---
        # The selectbox now correctly uses the comprehensive country_list variable.
        country_input_single = st.selectbox("Select Country of Import", country_list, key="country_single")

    if st.button("Calculate Tariffs", key="calc_single"):
        if not hts_input_single:
            st.warning("Please enter an HTS code.")
        else:
            with st.spinner('Performing lookup and AI analysis...'):
                hts_data = get_hts_data_from_file(hts_input_single)
                if hts_data:
                    st.session_state['single_hts_data'] = hts_data
                    rate_string = hts_data.get('General Rate of Duty', 'Free')
                    plan = get_calculation_plan_from_gemini(str(rate_string))
                    live_general_rate = plan.get('decimal_rate', 0.0)
                    results = calculate_all_tariffs(hts_input_single, country_input_single, all_dataframes, live_general_rate)
                    st.session_state['single_results'] = results
                    st.session_state['single_plan'] = plan
                else:
                    st.error(f"HTS Code '{hts_input_single}' not found in the data file.")
                    st.session_state['single_results'] = None

    if st.session_state.get('single_results'):
        results = st.session_state['single_results']
        plan = st.session_state['single_plan']
        hts_data = st.session_state['single_hts_data']

        st.info(f"**HTS Description:** {hts_data.get('HTS Description', 'N/A')}")
        if plan:
            st.success(f"**Rate Explanation:** {plan.get('explanation')}")
            if plan.get('requires_more_info'):
                st.warning("Note: The calculation below only includes the percentage-based portion of the duty.")

        st.subheader("Step 1: Tariff Component Breakdown")
        
        breakdown_data = []
        for scenario_name, result_data in results.items():
            row = {'Component': scenario_name}
            components = result_data.get('components', {})
            for comp_name, comp_rate in components.items():
                row[comp_name] = f"{comp_rate:.2%}"
            row['Total Tariff %'] = f"{result_data.get('Total Tariff %', 0):.2%}"
            breakdown_data.append(row)
        
        st.dataframe(pd.DataFrame(breakdown_data).set_index("Component"))

        st.markdown("---")
        st.subheader("Step 2: Calculate Total Cost")
        is_composite = list(results.values())[0].get('is_composite', False)
        if is_composite:
            st.markdown("This product is subject to Section 232. Please provide the value breakdown.")
            col1_val, col2_val = st.columns(2)
            metal_value = col1_val.number_input("Enter Metal Component Value ($):", min_value=0.0, format="%.2f", key="metal")
            other_value = col2_val.number_input("Enter Other Component Value ($):", min_value=0.0, format="%.2f", key="other")
            total_fob = metal_value + other_value
            if total_fob > 0:
                st.info(f"Total FOB Value: **${total_fob:,.2f}**")
        else:
            total_fob = st.number_input("Enter FOB Value ($):", min_value=0.0, format="%.2f", key="total")

        if total_fob > 0:
            landed_cost_data = []
            for scenario_name, result_data in results.items():
                row = {"Scenario": scenario_name}
                if is_composite:
                    metal_percent = result_data.get('Metal Component Tariff %', 0)
                    other_percent = result_data.get('Other Component Tariff %', 0)
                    total_tariff_value = (metal_value * metal_percent) + (other_value * other_percent)
                else:
                    total_tariff_value = total_fob * result_data.get('Total Tariff %', 0)

                row["Total Tariff Value"] = f"${total_tariff_value:,.2f}"
                row["Total Cost"] = f"${total_fob + total_tariff_value:,.2f}"
                landed_cost_data.append(row)
            st.table(pd.DataFrame(landed_cost_data).set_index("Scenario"))
        
        with st.expander("Show Detailed Component Breakdown (for debugging)"):
            for scenario_name, result_data in results.items():
                st.subheader(f"Details for: {scenario_name}")
                col1_detail, col2_detail = st.columns(2)
                with col1_detail:
                    st.markdown("**Component Rates:**")
                    for component_name, rate in result_data.get('components', {}).items():
                        st.markdown(f"- {component_name}: **{rate:.2%}**")
                with col2_detail:
                    st.markdown("**Scenario Totals:**")
                    if result_data.get('is_composite', False):
                        st.markdown(f"- Metal Tariff: **{result_data.get('Metal Component Tariff %', 0):.2%}**")
                        st.markdown(f"- Other Tariff: **{result_data.get('Other Component Tariff %', 0):.2%}**")
                    else:
                        st.markdown(f"- Total Tariff: **{result_data.get('Total Tariff %', 0):.2%}**")

# --- Tab 2: Multi Product Tariff ---
with tab2:
    st.header("Process a Bulk CSV File")
    st.markdown("Upload a CSV file with columns: `HTS_Code`, `Country of Import`, and `FOB Value`.")

    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")

    if uploaded_file is not None:
        try:
            input_df = pd.read_csv(uploaded_file, dtype={'HTS_Code': str})
            st.write("Preview of your uploaded data:")
            st.dataframe(input_df.head())

            if st.button("Process Full File", key="process_bulk"):
                result_df = process_bulk_upload(input_df)
                st.session_state['bulk_results'] = result_df

        except Exception as e:
            st.error(f"An error occurred while processing the file: {e}")
    
    if 'bulk_results' in st.session_state:
        st.subheader("Processing Complete")
        result_df = st.session_state['bulk_results']
        st.dataframe(result_df)
        
        @st.cache_data
        def convert_df_to_csv(df):
            return df.to_csv(index=False).encode('utf-8')

        csv_output = convert_df_to_csv(result_df)
        st.download_button(
            label="Download Results as CSV",
            data=csv_output,
            file_name='tariff_calculation_results.csv',
            mime='text/csv',
        )
