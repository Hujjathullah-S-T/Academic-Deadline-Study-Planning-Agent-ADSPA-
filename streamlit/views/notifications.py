"""In-app reminder center with opt-in browser desktop notifications."""
from __future__ import annotations

import streamlit as st


def render(agent, notification_component) -> None:
    data = agent.load_data()
    items = [item for item in data.get("notifications", []) if not item.get("read")]
    st.markdown("### Reminder center")
    if items:
        for item in reversed(items[-8:]):
            st.warning(f"**{item.get('title', 'Academic reminder')}** · {item.get('message', '')}")
        if st.button("Mark reminders as read", key="mark-reminders-read"):
            for item in data["notifications"]:
                item["read"] = True
            agent.save_data(data)
            st.rerun()
    else:
        st.caption("No unread reminders.")
    notification_component(notifications=items[-20:], key="desktop-notifications")


@st.fragment(run_every="1m")
def live_reminder_panel(agent, notification_component) -> None:
    render(agent, notification_component)
