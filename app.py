import json
from io import BytesIO

import pandas as pd
import streamlit as st
from docx import Document
from pypdf import PdfReader

from workflow_extractor import WorkflowExtractor


st.set_page_config(
    page_title="AI Workflow Copilot",
    page_icon="🤖",
    layout="wide",
)

extractor = WorkflowExtractor()


# -------------------------
# FILE TEXT EXTRACTION
# -------------------------

def extract_text_from_txt(uploaded_file) -> str:
    try:
        uploaded_file.seek(0)
        return uploaded_file.read().decode("utf-8")
    except UnicodeDecodeError:
        uploaded_file.seek(0)
        return uploaded_file.read().decode("latin-1", errors="ignore")
    except Exception:
        return ""


def extract_text_from_pdf(uploaded_file) -> str:
    try:
        uploaded_file.seek(0)
        pdf_bytes = uploaded_file.read()
        reader = PdfReader(BytesIO(pdf_bytes))

        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                pages.append(text)

        return "\n".join(pages).strip()
    except Exception:
        return ""


def extract_text_from_docx(uploaded_file) -> str:
    try:
        uploaded_file.seek(0)
        doc = Document(uploaded_file)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs).strip()
    except Exception:
        return ""


def load_uploaded_text(uploaded_file):
    if uploaded_file is None:
        return "", ""

    name = uploaded_file.name.lower()

    if name.endswith(".txt"):
        return extract_text_from_txt(uploaded_file), "Text File"

    if name.endswith(".pdf"):
        return extract_text_from_pdf(uploaded_file), "PDF"

    if name.endswith(".docx"):
        return extract_text_from_docx(uploaded_file), "Word Document"

    return "", ""


# -------------------------
# HELPER FUNCTIONS
# -------------------------

def priority_badge(priority: str) -> str:
    if priority == "High":
        return "🔴 High"
    if priority == "Medium":
        return "🟠 Medium"
    if priority == "Low":
        return "🟢 Low"
    return "-"


def safe_join_resources(resources) -> str:
    if isinstance(resources, list) and resources:
        return " | ".join(resources)
    return "-"


def build_task_dataframe(result):
    tasks = result.get("tasks", [])
    priorities = result.get("priorities", [])
    steps = result.get("workflow_steps", [])

    rows = []

    for i, task in enumerate(tasks):
        p = priorities[i] if i < len(priorities) else {}
        step = steps[i] if i < len(steps) else ""

        rows.append(
            {
                "Task": task.get("title", "") or "-",
                "Priority": p.get("priority", "") or "-",
                "Priority Reason": p.get("reason", "") or "-",
                "Due Date": task.get("due_date", "") or "-",
                "Category": task.get("category", "") or "-",
                "Assignee": task.get("assignee", "") or "-",
                "Location": task.get("location", "") or "-",
                "Resources": safe_join_resources(task.get("resources", [])),
                "Workflow Step": step or "-",
            }
        )

    return pd.DataFrame(rows)


def get_top_priority_task(result):
    tasks = result.get("tasks", [])
    priorities = result.get("priorities", [])
    steps = result.get("workflow_steps", [])

    if not tasks:
        return {}

    task = tasks[0]
    priority = priorities[0] if priorities else {}
    step = steps[0] if steps else "-"

    return {
        "title": task.get("title", "-"),
        "priority": priority.get("priority", "-"),
        "reason": priority.get("reason", "-"),
        "due_date": task.get("due_date", "-") or "-",
        "category": task.get("category", "-") or "-",
        "assignee": task.get("assignee", "-") or "-",
        "location": task.get("location", "-") or "-",
        "resources": task.get("resources", []) or [],
        "workflow_step": step,
    }


def filter_dataframe(df: pd.DataFrame, search_text: str, selected_priorities: list, selected_categories: list):
    filtered = df.copy()

    if search_text.strip():
        query = search_text.strip().lower()
        filtered = filtered[
            filtered.apply(
                lambda row: query in " ".join(str(value).lower() for value in row.values),
                axis=1,
            )
        ]

    if selected_priorities:
        filtered = filtered[filtered["Priority"].isin(selected_priorities)]

    if selected_categories:
        filtered = filtered[filtered["Category"].isin(selected_categories)]

    return filtered


# -------------------------
# UI HEADER
# -------------------------

st.title("🤖 AI Workflow Copilot")
st.caption("Turn notes, emails, and uploaded documents into a structured workflow plan.")

left_col, right_col = st.columns([1.35, 1])

# -------------------------
# INPUT SECTION
# -------------------------

with left_col:
    st.subheader("Input")

    input_mode = st.radio(
        "Choose input method",
        ["Paste Text", "Upload Document"],
        horizontal=True,
    )

    default_text = """Team meeting discussion:
We need to prepare the product presentation by Saturday 14 march 2027, update the sales dashboard, and send a summary email to stakeholders.
"""

    user_input = ""

    if input_mode == "Paste Text":
        user_input = st.text_area(
            "Paste meeting notes, task description, email, or multiple mixed requests",
            value=default_text,
            height=320,
            placeholder="Paste raw text here...",
        )
    else:
        uploaded_file = st.file_uploader(
            "Upload a document",
            type=["txt", "pdf", "docx"],
            help="Supported formats: TXT, PDF, DOCX",
        )

        if uploaded_file is not None:
            extracted_text, detected_type = load_uploaded_text(uploaded_file)

            if extracted_text:
                user_input = extracted_text
                st.success(f"{detected_type} loaded successfully.")

                with st.expander("Preview extracted text"):
                    st.text(extracted_text[:5000])
            else:
                st.error("Could not extract text from this file. Try a text-based TXT, PDF, or DOCX file.")

    generate = st.button("Generate Workflow Plan", use_container_width=True)

# -------------------------
# CAPABILITIES PANEL
# -------------------------

with right_col:
    st.subheader("Capabilities")
    st.markdown(
        """
- Extract tasks and action items  
- Detect due dates like `Friday`, `tomorrow`, `March 20`  
- Detect urgency words like `urgent`, `ASAP`, `immediately`  
- Detect assignee, location, category, and resources  
- Split mixed requests into multiple tasks  
- Support TXT, PDF, and DOCX uploads  
- Export results as JSON and CSV
"""
    )

# -------------------------
# MAIN PROCESSING
# -------------------------

if generate:
    if not user_input.strip():
        st.warning("Please paste text or upload a document first.")
        st.stop()

    result = extractor.extract_workflow(user_input)
    df = build_task_dataframe(result)
    top_task = get_top_priority_task(result)

    tasks = result.get("tasks", [])
    priorities = result.get("priorities", [])

    st.divider()
    st.subheader("Structured Workflow Output")

    high_count = sum(1 for item in priorities if item.get("priority") == "High")
    due_count = sum(1 for item in tasks if item.get("due_date"))
    resource_count = sum(1 for item in tasks if item.get("resources"))
    category_count = len({t.get("category") for t in tasks if t.get("category")})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tasks Found", len(tasks))
    c2.metric("High Priority", high_count)
    c3.metric("Tasks With Due Dates", due_count)
    c4.metric("Task Categories", category_count)

    if top_task:
        st.markdown("### Top Priority Task")
        with st.container(border=True):
            st.markdown(f"#### {top_task['title']}")
            st.write(f"**Priority:** {priority_badge(top_task['priority'])}")
            st.write(f"**Reason:** {top_task['reason']}")
            st.write(f"**Category:** {top_task['category']}")
            st.write(f"**Due Date:** {top_task['due_date']}")
            st.write(f"**Assignee:** {top_task['assignee']}")
            st.write(f"**Location:** {top_task['location']}")
            st.write(f"**Suggested Step:** {top_task['workflow_step']}")

            if top_task["resources"]:
                st.write("**Resources:**")
                for link in top_task["resources"]:
                    st.markdown(f"- {link}")

    st.markdown("### Filters")

    f1, f2, f3 = st.columns([1.2, 1, 1])

    with f1:
        search_text = st.text_input(
            "Search tasks",
            placeholder="Search by task, category, assignee, location...",
        )

    with f2:
        available_priorities = sorted(
            [value for value in df["Priority"].dropna().unique().tolist() if value != "-"]
        )
        selected_priorities = st.multiselect("Filter by priority", available_priorities)

    with f3:
        available_categories = sorted(
            [value for value in df["Category"].dropna().unique().tolist() if value != "-"]
        )
        selected_categories = st.multiselect("Filter by category", available_categories)

    filtered_df = filter_dataframe(df, search_text, selected_priorities, selected_categories)

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Task Board", "Task Table", "Workflow Steps", "Raw Output"]
    )

    with tab1:
        if filtered_df.empty:
            st.info("No tasks match the selected filters.")
        else:
            for _, row in filtered_df.iterrows():
                with st.container(border=True):
                    st.markdown(f"### {row['Task']}")
                    st.write(f"**Priority:** {priority_badge(row['Priority'])}")
                    st.write(f"**Reason:** {row['Priority Reason']}")
                    st.write(f"**Due Date:** {row['Due Date']}")
                    st.write(f"**Category:** {row['Category']}")
                    st.write(f"**Assignee:** {row['Assignee']}")
                    st.write(f"**Location:** {row['Location']}")
                    st.write(f"**Suggested Step:** {row['Workflow Step']}")

                    if row["Resources"] and row["Resources"] != "-":
                        st.write("**Resources:**")
                        for link in str(row["Resources"]).split(" | "):
                            st.markdown(f"- {link}")

    with tab2:
        if filtered_df.empty:
            st.info("No structured rows found.")
        else:
            st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    with tab3:
        if filtered_df.empty:
            st.info("No workflow steps found.")
        else:
            for i, step in enumerate(filtered_df["Workflow Step"].tolist(), start=1):
                st.markdown(f"**{i}.** {step}")

    with tab4:
        st.code(json.dumps(result, indent=2), language="json")

    st.divider()
    st.subheader("Download Results")

    json_data = json.dumps(result, indent=2)
    csv_data = filtered_df.to_csv(index=False)

    d1, d2 = st.columns(2)

    with d1:
        st.download_button(
            label="Download JSON",
            data=json_data,
            file_name="workflow_plan.json",
            mime="application/json",
            use_container_width=True,
        )

    with d2:
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name="workflow_plan.csv",
            mime="text/csv",
            use_container_width=True,
        )