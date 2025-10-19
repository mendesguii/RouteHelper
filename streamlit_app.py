def build_vatsim_icao_fpl(
    callsign: str,
    actype: str,
    wakecat: str,
    equipment: str,
    surveillance: str,
    dep_icao: str,
    dep_time: str,
    speed: str,
    level: str,
    route: str,
    dest_icao: str,
    eet: str,
    alt1: str = '',
    alt2: str = '',
    pbn: str = '',
    nav: str = '',
    rnp: str = '',
    dof: str = '',
    reg: str = '',
    sel: str = '',
    code: str = '',
    rvr: str = '',
    opr: str = '',
    per: str = '',
    rmk: str = ''
) -> str:
    # Compose the ICAO FPL message as a single line, as per user request
    # Only include fields that are not empty, in the correct order
    parts = [
        f"(FPL-{callsign}-IS",
        f"-{actype}/{wakecat}-{equipment}{surveillance}",
        f"-{dep_icao}{dep_time}",
        f"-{speed}{level} {route}".strip(),
        f"-{dest_icao}{eet} {alt1} {alt2}".strip(),
    ]
    # Optional fields, only if not empty
    if pbn: parts.append(f"-PBN/{pbn}")
    if nav: parts.append(f"NAV/{nav}")
    if rnp: parts.append(f"RNP{rnp}")
    if dof: parts.append(f"DOF/{dof}")
    if reg: parts.append(f"REG/{reg}")
    if eet: parts.append(f"EET/{eet}")
    if sel: parts.append(f"SEL/{sel}")
    if code: parts.append(f"CODE/{code}")
    if rvr: parts.append(f"RVR/{rvr}")
    if opr: parts.append(f"OPR/{opr}")
    if per: parts.append(f"PER/{per}")
    if rmk: parts.append(f"RMK/{rmk}")
    # Join all with spaces, close with )
    return ' '.join([p for p in parts if p.strip()]) + ")"
import os
import streamlit as st
from datetime import datetime
from main import RouteHelper


# Constants mirroring GUI
AIRCRAFT_OPTIONS = ["A319", "A320", "A321", "B738_ZIBO", "B738", "B737"]
DEFAULT_FL = "330"


def init_helper():
    if 'helper' not in st.session_state:
        st.session_state.helper = RouteHelper()
    return st.session_state.helper


def page_settings(helper: RouteHelper):
    with st.sidebar:
        with st.form(key="settings_form"):
            data_path = st.text_input("Data Folder (contains .dat)", value=helper.data_path or ".")
            cycle = st.number_input("AIRAC Cycle", min_value=1000, max_value=9999, value=int(getattr(helper, 'cycle', 2501)))
            apply_settings = st.form_submit_button("Apply", use_container_width=True)
        if apply_settings:
            helper.data_path = data_path
            try:
                helper.cycle = int(cycle)
            except Exception:
                helper.cycle = cycle
            st.success("Applied to this session")


def tab_procedures_metar(helper: RouteHelper):
    st.subheader("Procedures: SID/STAR")
    with st.form(key="proc_form"):
        c1, c2, c3 = st.columns([1,1,2])
        icao = c1.text_input("ICAO", key="proc_icao").upper().strip()
        proc_type = c2.selectbox("Type", ["SID", "STAR"], key="proc_type")
        fix = c3.text_input("Fix (optional)", key="proc_fix").upper().strip()
        search_btn = st.form_submit_button("Search", use_container_width=True)
    if search_btn:
        if not icao:
            st.warning("Enter an ICAO code.")
        else:
            try:
                helper.get_file_data(f'{helper.data_path}/{icao}.dat')
                if proc_type == 'SID':
                    if fix:
                        helper.plan = ''
                        helper.search_in_dict(helper.structure_data(helper.sids), fix)
                        st.text(helper.plan or "No results found.")
                    else:
                        st.json(helper.structure_data(helper.sids))
                else:
                    if fix:
                        helper.plan = ''
                        helper.search_in_dict(helper.structure_data(helper.stars), fix)
                        st.text(helper.plan or "No results found.")
                    else:
                        st.json(helper.structure_data(helper.stars))
            except Exception as e:
                st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("METAR ☁️")
    with st.form(key="metar_form"):
        col1 = st.columns(1)[0]
        metar_icao = col1.text_input("ICAO", key="metar_icao").upper().strip()
        metar_btn = st.form_submit_button("Get METAR", use_container_width=True)
    if metar_btn:
        if not metar_icao:
            st.warning("Enter an ICAO code.")
        else:
            try:
                helper.plan = ''
                helper.get_metar(metar_icao)
                st.text(helper.plan or "No METAR found.")
            except Exception as e:
                st.error(f"Error: {e}")


def build_ivao_fpl_content(helper: RouteHelper, origin: str, dest: str, plane: str) -> str:
    # Mirror gen_flight_plan without writing a file
    try:
        eet = helper.get_info_after('SI BLOCK TIME', helper.plan).replace(':', '') if helper.plan else ''
    except Exception:
        eet = ''
    try:
        endu = helper.get_info_after('TIME TO EMPTY', helper.plan).replace(':', '') if helper.plan else ''
    except Exception:
        endu = ''
    dof = 'DOF/' + datetime.today().strftime('%y%m%d')
    base = f"""[FLIGHTPLAN]
ID=XXXXXX
RULES=I
FLIGHTTYPE=S
NUMBER=1
ACTYPE={plane}
WAKECAT=M
EQUIPMENT=SDFGIRY
TRANSPONDER=S
DEPICAO={origin}
DEPTIME=
SPEEDTYPE=N
SPEED=
LEVELTYPE=F
LEVEL=330
ROUTE={' '.join(helper.route) if helper.route else ''}
DESTICAO={dest}
EET={eet}
ALTICAO=
ALTICAO2=
OTHER={dof}
ENDURANCE={endu}
POB=
"""
    return base


def tab_route_planner(helper: RouteHelper):
    st.subheader("Route Planner")
    with st.form(key="route_form"):
        col1, col2, col3 = st.columns(3)
        origin = col1.text_input("Origin ICAO", key="route_origin").upper().strip()
        dest = col2.text_input("Destination ICAO", key="route_dest").upper().strip()
        plane = col3.selectbox("Aircraft", AIRCRAFT_OPTIONS, key="route_plane")
        col4, col5 = st.columns(2)
        fl_start = col4.text_input("FL Start", value=DEFAULT_FL, key="fl_start").strip() or DEFAULT_FL
        fl_end = col5.text_input("FL End", value=DEFAULT_FL, key="fl_end").strip() or DEFAULT_FL
        plan_btn = st.form_submit_button("Plan Route", use_container_width=True)
    do_plan = plan_btn

    if do_plan:
        if not origin or not dest or not plane:
            st.warning("Please fill all fields.")
        else:
            # Loadsheet
            try:
                helper.get_fuel(origin, dest, plane)
                loadsheet = helper.plan or "No loadsheet generated."
            except Exception as e:
                loadsheet = f"Error: {e}"
            # Key metrics from parsed loadsheet (prominent)
            parsed = getattr(helper, 'parsed_loadsheet', None) or {}
            ttl = (parsed.get('weights', {}) or {}).get('total_traffic_load')
            tof = (parsed.get('weights', {}) or {}).get('takeoff_fuel')
            blk = (parsed.get('times', {}) or {}).get('block_time')
            endurance = (parsed.get('times', {}) or {}).get('time_to_empty')
            st.markdown("### Loadsheet summary")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Traffic Load (kg)", f"{ttl:,}" if isinstance(ttl, int) else (ttl or "N/A"))
            m2.metric("Take Off Fuel (kg)", f"{tof:,}" if isinstance(tof, int) else (tof or "N/A"))
            m3.metric("SI Block Time", blk or "N/A")
            m4.metric("Endurance", endurance or "N/A")
            with st.expander("Raw loadsheet text"):
                st.text(loadsheet)


            # Route
            try:
                helper.get_route(origin, dest, fl_start, fl_end, getattr(helper, 'cycle', 2501))
                route_text = ' '.join(helper.route) if helper.route else 'No route generated.'
            except Exception as e:
                route_text = f"Error: {e}"
            st.markdown("### Route")
            st.text_area("Route", value=route_text, height=100, label_visibility='collapsed')

            # SID/STAR fixes inferred from route ends
            sid_text = ""
            star_text = ""
            try:
                helper.get_file_data(f'{helper.data_path}/{origin}.dat')
                if helper.route:
                    helper.plan = ''
                    helper.search_in_dict(helper.structure_data(helper.sids), helper.route[0])
                    sid_text = helper.plan or "No SID fix found."
                else:
                    sid_text = "No SID fix found."
            except Exception as e:
                sid_text = f"Error: {e}"
            try:
                helper.get_file_data(f'{helper.data_path}/{dest}.dat')
                if helper.route:
                    helper.plan = ''
                    helper.search_in_dict(helper.structure_data(helper.stars), helper.route[-1])
                    star_text = helper.plan or "No STAR fix found."
                else:
                    star_text = "No STAR fix found."
            except Exception as e:
                star_text = f"Error: {e}"
            c_sid, c_star = st.columns(2)
            with c_sid:
                st.text_area("SID Fix Search (auto)", value=sid_text, height=150)
            with c_star:
                st.text_area("STAR Fix Search (auto)", value=star_text, height=150)

            # Manual SID/STAR Fix search
            st.markdown("---")
            ms1, ms2 = st.columns(2)
            with ms1:
                with st.form(key="sid_form"):
                    sid_fix = st.text_input("Search SID Fix", key="sid_fix").upper().strip()
                    sid_btn = st.form_submit_button("Search SID", use_container_width=True)
                if sid_btn:
                    try:
                        helper.get_file_data(f'{helper.data_path}/{origin}.dat')
                        helper.plan = ''
                        helper.search_in_dict(helper.structure_data(helper.sids), sid_fix)
                        st.text(helper.plan or "No SID fix found.")
                    except Exception as e:
                        st.error(f"Error: {e}")
            with ms2:
                with st.form(key="star_form"):
                    star_fix = st.text_input("Search STAR Fix", key="star_fix").upper().strip()
                    star_btn = st.form_submit_button("Search STAR", use_container_width=True)
                if star_btn:
                    try:
                        helper.get_file_data(f'{helper.data_path}/{dest}.dat')
                        helper.plan = ''
                        helper.search_in_dict(helper.structure_data(helper.stars), star_fix)
                        st.text(helper.plan or "No STAR fix found.")
                    except Exception as e:
                        st.error(f"Error: {e}")

            # METARs
            st.subheader("METAR ☁️")
            m1, m2 = st.columns(2)
            try:
                helper.plan = ''
                helper.get_metar(origin)
                m1.text(helper.plan or "No METAR found.")
            except Exception as e:
                m1.error(f"Error: {e}")
            try:
                helper.plan = ''
                helper.get_metar(dest)
                m2.text(helper.plan or "No METAR found.")
            except Exception as e:
                m2.error(f"Error: {e}")

            # Output only a single text area with the compiled flight plan
            st.markdown("---")
            # Use the current planned route and loadsheet to auto-fill the FPL as much as possible
            route_str = ' '.join(helper.route) if helper.route else ''
            parsed = getattr(helper, 'parsed_loadsheet', None) or {}
            # Example: auto-fill with some defaults, user can edit the text area if needed
            # Get SI BLOCK TIME from loadsheet for EET
            si_block_time = (parsed.get('times', {}) or {}).get('block_time', '')
            eet = si_block_time.replace(':', '') if si_block_time else ''
            msg = build_vatsim_icao_fpl(
                callsign="XXXXXX",
                actype=plane,
                wakecat="M",
                equipment="SDE3FGIJ1KRWXY/",
                surveillance="LB1",
                dep_icao=origin,
                dep_time="0000",
                speed="N0441",
                level=f"F{fl_start}",
                route=route_str,
                dest_icao=dest,
                eet=eet,
                alt1="",
                alt2="",
                pbn="A1B1D1O1S2",
                nav="RNVD1E2A1",
                rnp="2",
                dof=datetime.today().strftime('%y%m%d'),
                reg="",
                sel="",
                code="",
                rvr="",
                opr="",
                per="C",
                rmk="",
            )
            st.text_area("ICAO FPL (copy and paste to VATSIM)", value=msg, height=120, key="icao_fpl_output")


def main():
    st.set_page_config(page_title="RouteHelper (Streamlit)", layout="wide")
    helper = init_helper()

    # Sidebar navigation
    st.sidebar.title("RouteHelper")
    page_settings(helper)
    page = st.sidebar.radio("Navigation", ["Procedures / METAR", "Route Planner"], index=1)

    st.title("🛫 RouteHelper Web 🛬")
    if page == "Procedures / METAR":
        tab_procedures_metar(helper)
    else:
        tab_route_planner(helper)


if __name__ == "__main__":
    main()
