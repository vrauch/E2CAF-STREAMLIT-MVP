import streamlit as st
import pandas as pd
from src.meridant_client import get_client
from src import sql_templates as sql

def _download(df: pd.DataFrame, filename: str, label: str):
    if df is None or df.empty:
        st.info("Nothing to export yet.")
        return
    st.download_button(
        label=label,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
    )

def render():
    st.title("Simulation")
    st.caption("Create a scenario, define a capability change, run propagation, and export impacts.")

    client = get_client()

    uc = client.query(sql.q_list_next_usecases())
    df_uc = pd.DataFrame(uc.get("rows", []))
    if df_uc.empty:
        st.warning("No Next_UseCase records found.")
        return

    usecase_label = st.selectbox(
        "Select Use Case",
        df_uc.apply(lambda r: f'{r["id"]} — {r["usecase_title"]}', axis=1).tolist(),
        key="sim_usecase",
    )
    usecase_id = int(usecase_label.split("—")[0].strip())

    st.divider()
    st.subheader("Scenario")

    sc = client.query(sql.q_list_scenarios_for_usecase(usecase_id))
    df_sc = pd.DataFrame(sc.get("rows", []))

    create_new = st.checkbox("Create new scenario", value=df_sc.empty)
    if create_new:
        name = st.text_input("Scenario name", value="What-if Scenario")
        desc = st.text_area("Description", value="Simulate improving a capability and see downstream impacts.")
        if st.button("Create Scenario", type="primary"):
            try:
                client.write(sql.w_create_scenario(usecase_id, name, desc))
                st.success("Scenario created.")
                sc = client.query(sql.q_list_scenarios_for_usecase(usecase_id))
                df_sc = pd.DataFrame(sc.get("rows", []))
            except Exception as e:
                st.error(f"Create scenario failed: {e}")

    if df_sc.empty:
        st.warning("No scenarios available yet.")
        return

    scenario_label = st.selectbox(
        "Select Scenario",
        df_sc.apply(lambda r: f'{r["id"]} — {r["scenario_name"]}', axis=1).tolist(),
        key="sim_scenario",
    )
    scenario_id = int(scenario_label.split("—")[0].strip())

    st.divider()
    st.subheader("Define change")

    caps = client.query(sql.q_list_capabilities_for_usecase(usecase_id, limit=2000))
    df_caps = pd.DataFrame(caps.get("rows", []))
    
    if df_caps.empty:
        st.warning("No capabilities found.")
        return

    df_caps["label"] = df_caps.apply(
    lambda r: f'{int(r["id"])} — {r["capability_name"]} [{r.get("domain_name","?")} / {r.get("subdomain_name","?")}]',
    axis=1)

    cap_label = st.selectbox("Capability", df_caps["label"].tolist(), key="sim_cap")
    cap_id = int(cap_label.split("—")[0].strip())

    c1, c2, c3 = st.columns(3)
    with c1:
        dimension_id = st.number_input("Dimension ID", min_value=1, value=1, step=1)
    with c2:
        current = st.number_input("Current score", min_value=0, value=1, step=1)
    with c3:
        target = st.number_input("Target score", min_value=1, value=4, step=1)

    if st.button("Save change"):
        try:
            client.write(sql.w_set_scenario_change(scenario_id, cap_id, int(dimension_id), int(current), int(target)))
            st.success("Change saved.")
        except Exception as e:
            st.error(f"Save change failed: {e}")

    st.divider()
    st.subheader("Run propagation")

    max_depth = st.slider("Propagation depth", 1, 5, 3)
    if st.button("Run Simulation", type="primary"):
        try:
            client.write(sql.w_run_scenario(scenario_id, max_depth=max_depth))
            st.success("Simulation run complete.")
        except Exception as e:
            st.error(f"Run failed: {e}")

    st.divider()
    st.subheader("Impacted clusters")
    try:
        out = client.query(sql.q_scenario_impacts_cluster(scenario_id))
        df_out = pd.DataFrame(out.get("rows", []))
        st.dataframe(df_out, width='stretch')
        _download(df_out, f"scenario_{scenario_id}_cluster_impacts.csv", "Download cluster impacts (CSV)")
    except Exception:
        st.info("No cluster impacts yet (run simulation).")

    st.subheader("Impacted capabilities")
    try:
        out2 = client.query(sql.q_scenario_impacts_capability(scenario_id, limit=200))
        df_out2 = pd.DataFrame(out2.get("rows", []))
        st.dataframe(df_out2, width='stretch')
        _download(df_out2, f"scenario_{scenario_id}_capability_impacts.csv", "Download capability impacts (CSV)")
    except Exception:
        st.info("No capability impacts yet (run simulation).")
    
    show_all = st.checkbox("Show all capabilities (not just relevant)", value=False)
    if show_all:
        caps = client.query(sql.q_list_capabilities(limit=5000))
    else:
        caps = client.query(sql.q_list_capabilities_for_usecase(usecase_id, limit=2000))
    df_caps = pd.DataFrame(caps.get("rows", []))
  
    df_caps["label"] = df_caps.apply(
        lambda r: f'{int(r["id"])} — {r["capability_name"]} [{r.get("domain_name","?")} / {r.get("subdomain_name","?")}]',
        axis=1
    )

    cap_label = st.selectbox("Capability", df_caps["label"].tolist(), key="sim_cap_browse")
    cap_id = int(cap_label.split("—")[0].strip())
