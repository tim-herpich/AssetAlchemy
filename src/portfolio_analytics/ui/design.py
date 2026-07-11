from __future__ import annotations

import streamlit as st


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #f3f6f8;
            --surface: #ffffff;
            --surface-alt: #e9eef3;
            --ink: #162033;
            --muted: #647082;
            --line: #d7e0e8;
            --blue: #2457c5;
            --cyan: #007c89;
            --green: #1b7f5f;
            --red: #b43b45;
            --amber: #c47a23;
            --violet: #6953b8;
        }

        .stApp {
            background:
                linear-gradient(180deg, rgba(36, 87, 197, .055), rgba(36, 87, 197, 0) 260px),
                var(--bg);
            color: var(--ink);
        }

        .block-container {
            max-width: 1440px;
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }

        section[data-testid="stSidebar"] {
            background: #fbfcfe;
            border-right: 1px solid var(--line);
        }

        section[data-testid="stSidebar"] h1 {
            font-size: 1.25rem;
            margin-bottom: .35rem;
        }

        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #ffffff, #fbfcfe);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 12px 14px;
            box-shadow: 0 1px 2px rgba(22, 32, 51, .045);
        }

        div[data-testid="stMetricLabel"] p {
            color: var(--muted);
            font-weight: 650;
            font-size: .78rem;
        }

        div[data-testid="stMetricValue"] {
            color: var(--ink);
            font-weight: 760;
            font-size: 1.35rem;
        }

        [data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 8px;
            overflow: hidden;
            background: var(--surface);
        }

        .app-shell {
            border: 1px solid var(--line);
            border-radius: 8px;
            background:
                linear-gradient(135deg, rgba(36, 87, 197, .075), rgba(0, 124, 137, .035) 42%, rgba(255, 255, 255, 0) 72%),
                var(--surface);
            padding: 22px;
            box-shadow: 0 14px 34px rgba(22, 32, 51, .075);
        }

        .hero-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.45fr) minmax(280px, .85fr);
            gap: 18px;
            align-items: stretch;
        }

        .hero-title {
            font-size: clamp(2.1rem, 4vw, 4.1rem);
            line-height: 1.02;
            font-weight: 780;
            letter-spacing: 0;
            margin: 0 0 12px 0;
            color: var(--ink);
        }

        .hero-copy {
            color: var(--muted);
            font-size: 1.02rem;
            max-width: 760px;
            margin: 0 0 18px 0;
        }

        .status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 16px;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 6px 10px;
            color: var(--muted);
            background: #fff;
            font-size: .84rem;
            font-weight: 650;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: var(--cyan);
        }

        .contract-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            margin-top: 18px;
        }

        .contract-card, .insight-card {
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 14px;
            background: rgba(255, 255, 255, .84);
        }

        .contract-card h3, .insight-card h3 {
            margin: 0 0 8px 0;
            font-size: .92rem;
        }

        .contract-card p, .insight-card p {
            color: var(--muted);
            margin: 0;
            font-size: .86rem;
        }

        .start-panel {
            background:
                linear-gradient(180deg, rgba(22, 32, 51, .96), rgba(32, 49, 73, .96));
            color: #ffffff;
            border-radius: 8px;
            padding: 18px;
            min-height: 100%;
            border: 1px solid rgba(255, 255, 255, .10);
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
        }

        .start-panel-topline {
            color: #9fd7d8;
            text-transform: uppercase;
            letter-spacing: .08em;
            font-size: .72rem;
            font-weight: 780;
        }

        .start-panel-number {
            font-size: 5rem;
            line-height: .96;
            font-weight: 780;
            letter-spacing: 0;
            margin-top: 22px;
        }

        .start-panel-label {
            color: #d8e5ec;
            font-weight: 680;
            margin-top: 4px;
        }

        .start-panel-rule {
            height: 1px;
            width: 100%;
            background: rgba(255, 255, 255, .18);
            margin: 18px 0 14px 0;
        }

        .start-panel p {
            color: #b8c7d2;
            margin: 0;
            font-size: .9rem;
        }

        .section-kicker {
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: .08em;
            font-size: .72rem;
            font-weight: 760;
            margin-bottom: 5px;
        }

        .page-title {
            margin-bottom: 12px;
        }

        .insight-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin: 10px 0 18px 0;
        }

        .small-label {
            color: var(--muted);
            font-size: .78rem;
            font-weight: 700;
        }

        .big-value {
            color: var(--blue);
            font-weight: 780;
            font-size: 1.28rem;
            margin-top: 2px;
        }

        @media (max-width: 900px) {
            .hero-grid, .contract-grid, .insight-grid {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
