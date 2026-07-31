import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# הגדרות תצוגה בסיסיות לדף
st.set_page_config(page_title="לוח מתכונים", page_icon="🍳", layout="wide")

st.title("🍳 לוח המתכונים החכם שלי")

# יצירת הטאבים
tab_board, tab_add = st.tabs(["📋 לוח מתכונים", "➕ הוספת מתכון חדש"])

# --- טאב 2: הזנת נתונים ---
with tab_add:
    st.header("הזנת מתכון חדש באמצעות AI")
    with st.form("add_recipe_form"):
        recipe_url = st.text_input("לינק למתכון:")
        # אפשר כמובן להתאים את הקטגוריות
        category = st.selectbox("קטגוריה:", ["בשר", "עוף", "דגים", "צמחוני", "טבעוני", "מאפים", "קינוחים"])
        
        submit_button = st.form_submit_button("חלץ ושמור מתכון")
        
        if submit_button:
            if recipe_url:
                with st.spinner("מנתח את המתכון ומושך נתונים..."):
                    # כאן נכניס בהמשך את הקריאה למודל ה-AI
                    st.info("כאן ירוץ קוד ה-AI שיחלץ את הנתונים מהלינק (שם, מצרכים, תמונה) וישמור אותם ב-Google Sheets.")
            else:
                st.warning("אנא הזן לינק למתכון.")

# --- טאב 1: תצוגת לוח המתכונים ---
with tab_board:
    st.header("המתכונים שלי")
    # כאן נקרא בהמשך את הנתונים מ-Google Sheets ונציג אותם בכרטיסיות
    st.info("כאן תוצג גלריית המתכונים, מחולקת לפי הקטגוריות השונות.")
