# --- DIAGNOSTIC SCRIPT ---
# Temporarily replace the content of app.py with this to debug the file system.

import streamlit as st
import os

st.set_page_config(layout="wide")
st.title("🔍 File System Diagnostic Tool")
st.markdown("This tool shows what the Streamlit server's file system looks like.")

try:
    # Get the current working directory where the script is being run
    cwd = os.getcwd()
    st.header("1. Current Working Directory")
    st.code(cwd, language="bash")

    # List all items in that directory
    st.subheader("Items in the Current Directory:")
    items_in_cwd = os.listdir(cwd)
    if items_in_cwd:
        st.code('\n'.join(items_in_cwd), language="bash")
    else:
        st.warning("Current working directory is empty.")

    # Specifically check for the 'data' folder
    st.header("2. Checking for the 'data' folder")
    data_folder_path = os.path.join(cwd, 'data')
    st.write(f"Attempting to find folder at this exact path: `{data_folder_path}`")

    if os.path.exists(data_folder_path) and os.path.isdir(data_folder_path):
        st.success("✅ SUCCESS: The 'data' folder was found!")
        
        # List all items inside the 'data' folder
        st.subheader("Contents of the 'data' folder:")
        items_in_data = os.listdir(data_folder_path)
        if items_in_data:
            st.code('\n'.join(items_in_data), language="bash")
        else:
            st.warning("The 'data' folder exists, but it is empty.")
            
    else:
        st.error("❌ CRITICAL ERROR: The 'data' folder was NOT FOUND at the expected location.")
        st.write("This is the most likely reason your app is failing. Please check the folder name for exact case-sensitivity ('data', not 'Data') in your GitHub repository.")

except Exception as e:
    st.error(f"A critical error occurred while trying to run the diagnostic: {e}")