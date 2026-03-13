"""Use-Case Workspace – select a use case, manage intent, discover capabilities,
generate roadmaps, run investment optimisation, and produce an executive strategy."""

import streamlit as st
import pandas as pd
from src.meridant_client import get_client
from src.sql_templates import (
    q_list_next_usecases,
    q_list_tags,
    q_get_usecase_intent,
    w_replace_usecase_intent,
    q_discover_capabilities,
    w_init_target_maturity,
    w_generate_roadmap,
    q_roadmap_phase_counts,
    w_generate_cluster_roadmap,
    q_cluster_roadmap,
    w_run_investment,
    q_latest_investment_selection,
    w_generate_executive_strategy,
    q_latest_executive_strategy,
)

# ── helpers ────────────────────────────────────────────────────────────────

def _query_df(client, sql: str) -> pd.DataFrame:
    """Run a read query and return a DataFrame (empty on error)."""
    try:
        resp = client.query(sql)
        rows = resp.get("rows", resp.get("data", []))
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Query failed: {e}")
        return pd.DataFrame()


def _write(client, sql: str, success_msg: str = "Done.") -> bool:
    """Run a write query; show toast on success."""
    try:
        client.write(sql)
        st.success(success_msg)
        return True
    except Exception as e:
        st.error(f"Write failed: {e}")
        return False

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

# ── main render ────────────────────────────────────────────────────────────

def render() -> None:
    st.header("🗂️ Use-Case Workspace")
    client = get_client()

    # ── 1. Select a use case ──────────────────────────────────────────────
    uc_df = _query_df(client, q_list_next_usecases())
    if uc_df.empty:
        st.info("No use cases found. Make sure the API and database are set up.")
        return

    uc_options = dict(zip(uc_df["id"], uc_df["usecase_title"]))
    selected_id = st.selectbox(
        "Select a Use Case",
        options=list(uc_options.keys()),
        format_func=lambda x: f"{x} — {uc_options[x]}",
    )

    tabs = st.tabs([
        "Intent Tags",
        "Capabilities",
        "Roadmap",
        "Cluster Roadmap",
        "Investment",
        "Executive Strategy",
    ])

    # ── 2. Intent Tags ────────────────────────────────────────────────────
    with tabs[0]:
        st.subheader("Current Intent Tags")
        intent_df = _query_df(client, q_get_usecase_intent(selected_id))
        if not intent_df.empty:
            st.dataframe(intent_df, width='stretch')
        else:
            st.info("No intent tags assigned yet.")

        with st.expander("Assign / update intent tags"):
            tag_df = _query_df(client, q_list_tags())
            if tag_df.empty:
                st.warning("No capability tags available.")
            else:
                tag_options = dict(zip(tag_df["id"], tag_df["tag_name"]))
                chosen_tags = st.multiselect(
                    "Tags",
                    options=list(tag_options.keys()),
                    format_func=lambda x: tag_options[x],
                    default=list(intent_df["tag_id"]) if not intent_df.empty and "tag_id" in intent_df.columns else [],
                )
                weight = st.slider("Default weight for new tags", 1, 10, 5)
                if st.button("Save Intent Tags"):
                    tw = {tid: weight for tid in chosen_tags}
                    _write(client, w_replace_usecase_intent(selected_id, tw), "Intent tags saved.")

    # ── 3. Discover Capabilities ──────────────────────────────────────────
    with tabs[1]:
        st.subheader("Discovered Capabilities")
        cap_df = _query_df(client, q_discover_capabilities(selected_id))
        if not cap_df.empty:
            st.dataframe(cap_df, width='stretch')
        else:
            st.info("Assign intent tags first to discover matching capabilities.")

        col_a, col_b = st.columns(2)
        with col_a:
            dim_id = st.number_input("Dimension ID", value=1, min_value=1, step=1)
        with col_b:
            target = st.number_input("Default target score", value=3, min_value=1, max_value=5, step=1)
        if st.button("Initialise Target Maturity"):
            _write(client, w_init_target_maturity(selected_id, dim_id, target),
                   "Target maturity initialised.")

    # ── 4. Roadmap ────────────────────────────────────────────────────────
    with tabs[2]:
        st.subheader("Capability Roadmap")
        if st.button("Generate Roadmap"):
            _write(client, w_generate_roadmap(selected_id), "Roadmap generated.")

        phase_df = _query_df(client, q_roadmap_phase_counts(selected_id))
        if not phase_df.empty:
            st.bar_chart(phase_df.set_index("phase"))
            st.dataframe(phase_df, width='stretch')
        else:
            st.info("No roadmap data yet. Click 'Generate Roadmap' above.")

    # ── 5. Cluster Roadmap ────────────────────────────────────────────────
    with tabs[3]:
        st.subheader("Cluster Roadmap")
        if st.button("Generate Cluster Roadmap"):
            _write(client, w_generate_cluster_roadmap(selected_id),
                   "Cluster roadmap generated.")

        cluster_df = _query_df(client, q_cluster_roadmap(selected_id))
        if not cluster_df.empty:
            st.dataframe(cluster_df, width='stretch')
        else:
            st.info("No cluster roadmap yet. Generate the capability roadmap first.")

    # ── 6. Investment Optimisation ────────────────────────────────────────
    with tabs[4]:
        st.subheader("Investment Optimisation")
        budget = st.number_input("Budget", value=1_000_000.0, step=50_000.0, format="%.0f")
        if st.button("Run Investment Analysis"):
            _write(client, w_run_investment(selected_id, budget),
                   "Investment analysis complete.")

        inv_df = _query_df(client, q_latest_investment_selection(selected_id))
        if not inv_df.empty:
            st.dataframe(inv_df, width='stretch')
        else:
            st.info("No investment results yet.")

    # ── 7. Executive Strategy ─────────────────────────────────────────────
    with tabs[5]:
        st.subheader("Executive Strategy")
        title = st.text_input("Strategy title", value=uc_options.get(selected_id, ""))
        if st.button("Generate Executive Strategy"):
            _write(client, w_generate_executive_strategy(selected_id, title),
                   "Executive strategy generated.")

        strat_df = _query_df(client, q_latest_executive_strategy(selected_id))
        if not strat_df.empty:
            row = strat_df.iloc[0]
            for col_name in strat_df.columns:
                if col_name not in ("id", "usecase_id", "created_on"):
                    st.markdown(f"**{col_name.replace('_', ' ').title()}:** {row[col_name]}")
        else:
            st.info("No executive strategy generated yet.")
