from __future__ import annotations

import streamlit as st


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --aa-ink: #142033;
            --aa-muted: #697586;
            --aa-line: #e4e9ef;
            --aa-surface: #ffffff;
            --aa-bg: #f8fafc;
            --aa-accent: #087a78;
            --aa-accent-dark: #066462;
        }

        .stApp { background: var(--aa-bg); color: var(--aa-ink); }
        .block-container { max-width: 1520px; padding-top: 2rem; padding-bottom: 2.5rem; }
        section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid var(--aa-line); }
        section[data-testid="stSidebar"] > div { padding-top: 1.35rem; }

        .brand-mark {
            color: var(--aa-ink); font-size: 1.18rem; font-weight: 750;
            letter-spacing: -.025em; margin-bottom: .2rem;
        }
        .eyebrow, .section-label {
            color: var(--aa-muted); font-size: .72rem; font-weight: 720;
            letter-spacing: .09em; text-transform: uppercase;
        }
        .section-label { margin: 1.4rem 0 .55rem; }
        .lead { color: var(--aa-muted); font-size: 1.15rem; margin: -.35rem 0 .5rem; }

        h1, h2, h3 { color: var(--aa-ink) !important; letter-spacing: -.03em; }
        h1 { font-weight: 720 !important; margin-bottom: .3rem !important; }
        h2, h3 { font-weight: 680 !important; }
        p, .stCaption { color: var(--aa-muted); }

        div[data-testid="stMetric"] {
            background: var(--aa-surface); border: 1px solid var(--aa-line);
            border-radius: 10px; padding: .75rem .85rem; box-shadow: none;
            min-height: 0;
        }
        div[data-testid="stMetricLabel"] p {
            color: var(--aa-muted); font-size: .72rem; font-weight: 650;
        }
        div[data-testid="stMetricValue"] { color: var(--aa-ink); font-size: 1.22rem; font-weight: 720; }

        .stButton > button, .stDownloadButton > button {
            border-radius: 8px; min-height: 2.35rem; font-weight: 650;
            border-color: #cfd8e3; box-shadow: none;
        }
        .stButton > button[kind="primary"] {
            background: var(--aa-accent); border-color: var(--aa-accent); color: white;
        }
        .stButton > button[kind="primary"]:hover { background: var(--aa-accent-dark); border-color: var(--aa-accent-dark); }
        div[data-testid="stFileUploader"] { border-radius: 9px; }
        div[data-testid="stFileUploaderDropzone"] { background: #fbfcfd; border: 1px dashed #cbd5df; border-radius: 9px; padding: .6rem; }

        button[data-baseweb="tab"] { color: var(--aa-muted); font-size: .84rem; font-weight: 650; padding: .6rem .7rem; }
        button[data-baseweb="tab"][aria-selected="true"] { color: var(--aa-accent); }
        [data-testid="stDataFrame"] { border: 1px solid var(--aa-line); border-radius: 9px; overflow: hidden; background: white; }
        [data-testid="stExpander"] { border: 1px solid var(--aa-line); border-radius: 9px; background: white; }

        .workflow { margin-top: 1.4rem; }
        .workflow-step {
            background: var(--aa-surface); border: 1px solid var(--aa-line); border-radius: 10px;
            min-height: 140px; padding: 1rem 1.05rem;
        }
        .workflow-step span { color: var(--aa-accent); font-size: .74rem; font-weight: 750; letter-spacing: .08em; }
        .workflow-step h3 { font-size: .98rem; margin: .65rem 0 .35rem; }
        .workflow-step p { font-size: .86rem; line-height: 1.45; margin: 0; }

        .js-plotly-plot .plotly .main-svg { border-radius: 8px; }
        @media (max-width: 900px) {
            .block-container { padding-top: 1.25rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
