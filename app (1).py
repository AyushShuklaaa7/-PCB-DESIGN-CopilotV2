import streamlit as st
import pandas as pd
import io
import json
import hashlib
import urllib.parse
from google import genai
from google.genai import types

st.set_page_config(page_title="Advanced EDA Copilot & BOM Engine", page_icon="🎛️", layout="wide")

st.title("🎛️ EDA System Copilot: Architecture, Review & BOM Engine")
st.write("Upload component datasheets and describe your project intent to generate block diagrams, pin connections, missing passive advice, stackup strategy, and KiCad BOM exports with SnapMagic model links.")

with st.sidebar:
    st.header("🔑 Authentication & Setup")
    api_key = st.text_input("Enter Gemini API Key:", type="password")
    st.markdown("[Get a free API key here](https://aistudio.google.com/)")
    st.write("---")
    st.info("💡 Tip: Upload all main IC datasheets (MCU, Transceivers, Regulators, Sensors) alongside your functional prompt.")

# 1. User Intent Prompt Input
user_project_prompt = st.text_area(
    "💬 Describe your project intent & target features:",
    placeholder="e.g., A battery-powered handheld controller with USB-C charging, BLE connectivity, 6-DOF IMU motion sensing, and I2C status displays."
)

# 2. File Uploader
uploaded_files = st.file_uploader(
    "📂 Ingest Project Datasheets (Upload multiple PDFs)",
    type=["pdf"],
    accept_multiple_files=True
)

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "bom": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "designator": {"type": "string"},
                    "part_number": {"type": "string"},
                    "package": {"type": "string"},
                    "operating_voltage": {"type": "string"},
                    "max_current": {"type": "string"},
                    "tolerance_or_key_spec": {"type": "string"},
                },
                "required": ["designator", "part_number", "package"],
            },
        },
        "project_analysis": {"type": "string"},
        "mermaid_diagram": {"type": "string"},
        "pin_routing_table": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_ic_pin": {"type": "string"},
                    "target_ic_pin": {"type": "string"},
                    "signal_type": {"type": "string"},
                    "notes": {"type": "string"}
                },
                "required": ["source_ic_pin", "target_ic_pin", "signal_type"]
            }
        },
        "missing_support_components": {
            "type": "array",
            "items": {"type": "string"}
        },
        "pcb_specs": {
            "type": "object",
            "properties": {
                "recommended_layers": {"type": "integer"},
                "estimated_dimensions_mm": {"type": "string"},
                "footprint_advice": {"type": "string"}
            },
            "required": ["recommended_layers", "estimated_dimensions_mm", "footprint_advice"]
        },
        "compatibility": {"type": "string"},
        "impedance": {"type": "string"},
        "citations": {"type": "string"},
    },
    "required": [
        "bom", "project_analysis", "mermaid_diagram", "pin_routing_table",
        "missing_support_components", "pcb_specs", "compatibility", "impedance", "citations"
    ],
}

SYSTEM_PROMPT = """
You are an expert senior hardware design engineer and hardware QA auditor. Analyze the attached component datasheets alongside the user's project intent prompt.

Perform a complete hardware architecture analysis and generate the JSON response matching the schema:

1. "bom": Consolidated Bill of Materials. Field values must be accurate to the datasheets or "Not specified".
2. "project_analysis": Concise evaluation comparing user intent against the capabilities of uploaded ICs.
3. "mermaid_diagram": Raw valid Mermaid graph syntax (e.g. `graph TD ...`) illustrating power rails, controllers, buses, and peripherals.
4. "pin_routing_table": Suggested pin-to-pin mapping between ICs (e.g., MCU SPI/I2C/GPIO pins to Peripheral pins).
5. "missing_support_components": Recommended passives, pull-up resistors, crystal load caps, decoupling caps, ESD protection, or LDOs omitted from raw datasheets.
6. "pcb_specs": Recommended layer count (2, 4, 6 layer), estimated PCB board area in mm, and thermal/footprint routing guidelines.
7. "compatibility": Rail alignment, clock tolerances, logic level translation needs, or thermal flags.
8. "impedance": High-speed differential pairs (USB 90Ω, Ethernet 100Ω, RF 50Ω antenna traces) requiring impedance control.
9. "citations": Page references and source file citations for critical specs.

Respond strictly with valid JSON adhering to the given schema.
"""

def generate_snapmagic_link(mpn):
    if not mpn or mpn == "Not specified":
        return "N/A"
    encoded_mpn = urllib.parse.quote(mpn.strip())
    return f"https://www.snapmagic.com/search/?q={encoded_mpn}"

@st.cache_data(show_spinner=False)
def run_review(file_hashes, file_bytes_list, api_key, user_prompt_text):
    client = genai.Client(api_key=api_key)
    contents_payload = [
        types.Part.from_bytes(data=fb, mime_type="application/pdf") for fb in file_bytes_list
    ]
    
    full_prompt = f"User Target Project Intent:\n{user_prompt_text}\n\nSystem Audit Instructions:\n{SYSTEM_PROMPT}"
    contents_payload.append(full_prompt)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents_payload,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )
    return response.text

if uploaded_files and len(uploaded_files) > 0:
    st.success(f"Staged {len(uploaded_files)} datasheets into processing memory.")
    
    if st.button("🚀 Run Complete EDA Review & Architecture Pipeline"):
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar.")
        else:
            with st.spinner("Analyzing architecture, mapping pin nets, and generating PCB layout parameters..."):
                try:
                    file_bytes_list = [f.read() for f in uploaded_files]
                    combined_hash = hashlib.sha256(b"".join(file_bytes_list) + user_project_prompt.encode()).hexdigest()

                    raw_json_text = run_review(combined_hash, tuple(file_bytes_list), api_key, user_project_prompt)
                    st.session_state["review_result"] = json.loads(raw_json_text)
                    st.session_state["review_error"] = None
                except Exception as e:
                    st.session_state["review_error"] = f"Pipeline Execution Failed: {e}"
                    st.session_state["review_result"] = None

    if "review_result" in st.session_state and st.session_state["review_result"]:
        res = st.session_state["review_result"]

        tab_bom, tab_diagram, tab_pins, tab_pcb, tab_drc, tab_verify = st.tabs([
            "📋 BOM & SnapMagic Links",
            "🧩 Block Diagram",
            "🔌 Pin-to-Pin Connections",
            "📐 PCB Strategy & Passives",
            "❌ DRC & Impedance Rules",
            "📖 Citations & Logs"
        ])

        with tab_bom:
            st.markdown("### Bill of Materials & Symbol/Footprint Downloads")
            bom_list = res.get("bom", [])
            if bom_list:
                df = pd.DataFrame(bom_list)
                # Add SnapMagic Search URL
                df["SnapMagic_Link"] = df["part_number"].apply(generate_snapmagic_link)
                
                st.dataframe(
                    df,
                    column_config={
                        "SnapMagic_Link": st.column_config.LinkColumn(
                            "Footprint & Symbol Link",
                            display_text="Download on SnapMagic"
                        )
                    },
                    use_container_width=True
                )

                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                st.download_button(
                    label="💾 Export KiCad-Ready CSV BOM",
                    data=csv_buffer.getvalue(),
                    file_name="kicad_system_bom.csv",
                    mime="text/csv"
                )

        with tab_diagram:
            st.markdown("### Functional Block Diagram")
            st.markdown(res.get("project_analysis", ""))
            mermaid_code = res.get("mermaid_diagram", "")
            if mermaid_code:
                st.markdown(f"```mermaid\n{mermaid_code}\n```")

        with tab_pins:
            st.markdown("### Recommended IC Pin Connections")
            pin_data = res.get("pin_routing_table", [])
            if pin_data:
                st.dataframe(pd.DataFrame(pin_data), use_container_width=True)

        with tab_pcb:
            st.markdown("### Physical Layout, Stackup & Missing Components")
            specs = res.get("pcb_specs", {})
            
            c1, c2 = st.columns(2)
            c1.metric("Recommended Stackup Layers", f"{specs.get('recommended_layers', 'N/A')} Layers")
            c2.metric("Estimated Board Area", specs.get("estimated_dimensions_mm", "N/A"))

            st.subheader("Footprint & PCB Routing Advice")
            st.info(specs.get("footprint_advice", "No specific layout notes."))

            st.subheader("Recommended Extra Passives & Support ICs")
            extra_comps = res.get("missing_support_components", [])
            for item in extra_comps:
                st.write(f"• {item}")

        with tab_drc:
            st.markdown("### Compatibility Checks & Controlled Impedance")
            st.subheader("Rail & System Compatibility")
            st.write(res.get("compatibility", ""))
            st.subheader("High-Speed Routing & Impedance Nets")
            st.write(res.get("impedance", ""))

        with tab_verify:
            st.markdown("### Source Verification Ledger")
            st.write(res.get("citations", ""))

    elif "review_error" in st.session_state and st.session_state["review_error"]:
        st.error(st.session_state["review_error"])
