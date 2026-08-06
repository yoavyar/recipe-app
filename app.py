import streamlit as st
import pandas as pd
import threading
import re
from streamlit.runtime.scriptrunner import add_script_run_ctx
from streamlit_gsheets import GSheetsConnection
from extractor import extract_recipe_data

st.set_page_config(page_title="לוח מתכונים", page_icon="🍳", layout="wide")

# --- עיצוב מותאם לעברית (RTL) ---
st.markdown("""
<style>
    .stApp, .block-container { direction: rtl; text-align: right; }
    p, div, input, label, h1, h2, h3, h4, h5, h6, span { text-align: right; }
    .streamlit-expanderHeader { direction: rtl; font-size: 1.1rem; font-weight: bold; }
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea, div[data-baseweb="select"] div { direction: rtl; text-align: right; }
    div[data-baseweb="tab-list"] { justify-content: flex-start; direction: rtl; }
    div[role="dialog"] { direction: rtl; text-align: right; }
</style>
""", unsafe_allow_html=True)

conn = st.connection("gsheets", type=GSheetsConnection)

# --- חלון פופ-אפ לווידוא מחיקה ---
@st.dialog("מחיקת מתכון")
def confirm_delete(index):
    st.warning("האם ברצונך למחוק את המתכון מהלוח?")
    cols = st.columns(2)
    with cols[0]:
        if st.button("בטל", use_container_width=True):
            st.rerun()
    with cols[1]:
        if st.button("מחק", type="primary", use_container_width=True):
            fresh_df = conn.read(ttl=0)
            fresh_df = fresh_df.drop(index)
            conn.update(data=fresh_df)
            st.cache_data.clear()
            st.rerun()

# --- מנגנון ריצה ברקע (Fire and Forget) ---
def process_recipe_background(url, category, notes, api_key):
    try:
        ai_data = extract_recipe_data(url, category, api_key)
        
        if ai_data and "error" not in ai_data:
            thread_conn = st.connection("gsheets", type=GSheetsConnection)
            df = thread_conn.read(ttl=0)
            
            new_row = pd.DataFrame([{
                "Category": category,
                "Recipe_Name": ai_data.get("Recipe_Name", ""),
                "Ingredients": ai_data.get("Ingredients", ""),
                "Image_URL": ai_data.get("Image_URL", ""),
                "Recipe_URL": url,
                "Notes": notes
            }])
            
            if df.empty or len(df.columns) == 0:
                updated_df = new_row
            else:
                updated_df = pd.concat([df, new_row], ignore_index=True)
            
            thread_conn.update(data=updated_df)
            st.cache_data.clear()
            
    except Exception as e:
        print(f"Background task failed: {e}")

st.title("🍳 לוח המתכונים")

tab_board, tab_add = st.tabs(["📋 לוח מתכונים", "➕ הוספת מתכון חדש"])
categories_list = ["עוף", "בשר", "דגים", "תוספות", "מרק", "סלטים", "קינוחים"]

# --- טאב הזנה ---
with tab_add:
    st.header("הזנת מתכון חדש")
    with st.form("add_recipe"):
        url_input = st.text_input("הכנס לינק למתכון (אתר או אינסטגרם):")
        category_input = st.selectbox("קטגוריה:", categories_list)
        notes_input = st.text_area("הערות (אופציונלי):", placeholder="לדוגמה: להפחית חצי כוס סוכר, להשתמש בקמח כוסמין...")
        
        submit = st.form_submit_button("שלח לעיבוד")
        
        if submit and url_input:
            # ניקוי הלינק: מחלץ רק את הכתובת האמיתית ומתעלם מכל טקסט אחר שהודבק בטעות
            url_match = re.search(r'(https?://[^\s]+)', url_input)
            clean_url = url_match.group(1) if url_match else url_input.strip()
            
            api_key = st.secrets["AI_API_KEY"]
            
            thread = threading.Thread(target=process_recipe_background, args=(clean_url, category_input, notes_input, api_key))
            add_script_run_ctx(thread)
            thread.start()
            
            st.success("הבקשה נשלחה לעיבוד ברקע! 🚀 אפשר לסגור את האפליקציה, המתכון יתווסף ללוח בעוד מספר שניות.")

# --- טאב לוח תצוגה ---
with tab_board:
    st.header("המתכונים שלי")
    try:
        df = conn.read(ttl=0).fillna("")
        
        if df.empty or len(df.columns) == 0:
            st.info("לוח המתכונים כרגע ריק. הוסף את המתכון הראשון שלך בטאב השני.")
        else:
            categories = [c for c in df['Category'].unique() if c != ""]
            
            for cat in categories:
                with st.expander(f"🍽️ קטגוריה: {cat}", expanded=False):
                    cat_df = df[df['Category'] == cat]
                    
                    cols = st.columns(4)
                    for i, (index, row) in enumerate(cat_df.iterrows()):
                        col = cols[i % 4]
                        with col:
                            with st.container(border=True):
                                # טיפול בתמונות שבורות (חסימת Hotlink של אינסטגרם/פייסבוק)
                                img_url = str(row.get('Image_URL', ''))
                                if img_url and img_url.startswith('http'):
                                    # אם זו תמונה מאינסטגרם, אנחנו נדלג עליה כדי שלא תופיע כתמונה שבורה
                                    if "scontent" not in img_url and "instagram" not in img_url:
                                        st.image(img_url, use_container_width=True)
                                
                                recipe_name = row.get('Recipe_Name', '')
                                st.markdown(f"**{recipe_name if recipe_name else 'מתכון ללא שם'}**")
                                
                                with st.expander("מצרכים"):
                                    st.text(row.get('Ingredients', 'אין מצרכים זמינים'))
                                
                                notes = str(row.get('Notes', ''))
                                if notes and notes != 'nan':
                                    st.info(f"**הערות:** {notes}")
                                
                                # ניקוי הלינק למקרה שנשמר בעבר לינק מלוכלך בטבלה (כמו במקרה שלך)
                                recipe_url = str(row.get('Recipe_URL', '#'))
                                display_url_match = re.search(r'(https?://[^\s]+)', recipe_url)
                                display_url = display_url_match.group(1) if display_url_match else recipe_url
                                
                                action_cols = st.columns([1, 2])
                                with action_cols[0]:
                                    if st.button("🗑️", key=f"del_{index}", help="מחק מתכון זה"):
                                        confirm_delete(index)
                                with action_cols[1]:
                                    st.markdown(f"[🔗 למתכון המלא]({display_url})")
                                    
    except Exception as e:
        st.error(f"שגיאה בקריאת הנתונים: {e}")
