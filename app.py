import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import re
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="לוח מתכונים", page_icon="🍳", layout="wide")

# --- עיצוב מותאם לעברית (RTL) ---
st.markdown("""
<style>
    /* הפיכת כיוון האפליקציה מימין לשמאל */
    .stApp, .block-container {
        direction: rtl;
        text-align: right;
    }
    
    /* יישור כללי של טקסטים, כותרות ותוויות לימין */
    p, div, input, label, h1, h2, h3, h4, h5, h6, span {
        text-align: right;
    }
    
    /* סידור חלוניות המצרכים (Expanders) */
    .streamlit-expanderHeader {
        direction: rtl;
    }
    
    /* יישור שדות קלט (לינקים) ותפריטים נפתחים (קטגוריות) */
    div[data-baseweb="input"] input, div[data-baseweb="select"] div {
        direction: rtl;
        text-align: right;
    }
    
    /* סידור הטאבים העליונים שיתחילו מימין */
    div[data-baseweb="tab-list"] {
        justify-content: flex-start;
        direction: rtl;
    }
    
    /* יישור חלון הפופ-אפ של המחיקה (Modal) */
    div[role="dialog"] {
        direction: rtl;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# יצירת אובייקט חיבור ל-Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- חלון פופ-אפ לווידוא מחיקה ---
@st.dialog("מחיקת מתכון")
def confirm_delete(index):
    st.warning("האם ברצונך למחוק את המתכון מהלוח?")
    cols = st.columns(2)
    with cols[0]:
        # כפתור ביטול
        if st.button("בטל", use_container_width=True):
            st.rerun()
    with cols[1]:
        # כפתור מחיקה בולט
        if st.button("מחק", type="primary", use_container_width=True):
            fresh_df = conn.read(ttl=0)
            fresh_df = fresh_df.drop(index)
            conn.update(data=fresh_df)
            st.cache_data.clear()
            st.rerun()

# --- מנגנון ה-AI לחילוץ הנתונים ---
def extract_recipe_data(url, category):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'utf-8'
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        meta_title = soup.find('meta', property='og:title')
        meta_title = meta_title['content'] if meta_title else ""
        
        meta_image = soup.find('meta', property='og:image')
        meta_image = meta_image['content'] if meta_image else ""
        
        text_content = soup.get_text(separator='\n', strip=True)
        images = [img.get('src') for img in soup.find_all('img') if img.get('src') and img.get('src').startswith('http')]
        
        if meta_image and meta_image not in images:
            images.insert(0, meta_image)
            
        images_list = "\n".join(images[:15])
        
        genai.configure(api_key=st.secrets["AI_API_KEY"])
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if not available_models:
            st.error("לא נמצאו מודלים זמינים בחשבון.")
            return None
            
        prompt = f'''
        You are an advanced recipe data extractor. 
        Extract the recipe details into a strictly valid JSON object.
        
        Required JSON structure:
        {{
            "Recipe_Name": "The exact name of the recipe in Hebrew",
            "Ingredients": "The list of ingredients in Hebrew, separated by a newline character (\\n)",
            "Image_URL": "The best matching high-resolution image URL"
        }}
        
        Metadata Title (Extremely Important): {meta_title}
        Metadata Image (Extremely Important): {meta_image}
        
        Website Text (partial):
        {text_content[:15000]}
        
        Potential Image URLs:
        {images_list}
        
        Instructions: 
        1. Always use the Metadata Title for "Recipe_Name" if available.
        2. Always use the Metadata Image for "Image_URL" if available.
        3. If you cannot find ingredients in the Website Text, use your extensive culinary knowledge to estimate the ingredients based on the Metadata Title, but try to extract them from the text first.
        '''
        
        data = None
        preferred_models = ['models/gemini-3.1-pro', 'models/gemini-3.1-flash', 'models/gemini-3.0-pro', 'models/gemini-3.0-flash']
        models_to_try = [m for m in preferred_models if m in available_models] + [m for m in available_models if m not in preferred_models]
        
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                res_text = response.text.strip()
                
                json_match = re.search(r'\{.*\}', res_text, re.DOTALL)
                if json_match:
                    res_text = json_match.group(0)
                    
                data = json.loads(res_text)
                
                if data.get("Recipe_Name"):
                    break 
                    
            except Exception:
                continue
                
        return data
        
    except Exception as e:
        st.error(f"שגיאה כללית בחילוץ: {e}")
        return None

# --- ממשק המשתמש ---
st.title("🍳 לוח המתכונים")

tab_board, tab_add = st.tabs(["📋 לוח מתכונים", "➕ הוספת מתכון חדש"])

with tab_add:
    st.header("הזנת מתכון חדש")
    with st.form("add_recipe"):
        url_input = st.text_input("הכנס לינק למתכון:")
        category_input = st.selectbox("קטגוריה:", ["בשר", "עוף", "דגים", "חלבי", "צמחוני", "טבעוני", "מאפים", "קינוחים", "שונות"])
        submit = st.form_submit_button("חלץ ושמור מתכון")
        
        if submit and url_input:
            with st.spinner("מנתח את העמוד ומחלץ נתונים (זה עשוי לקחת כמה שניות)..."):
                ai_data = extract_recipe_data(url_input, category_input)
                
                if ai_data:
                    try:
                        df = conn.read(ttl=0)
                        
                        new_row = pd.DataFrame([{
                            "Category": category_input,
                            "Recipe_Name": ai_data.get("Recipe_Name", ""),
                            "Ingredients": ai_data.get("Ingredients", ""),
                            "Image_URL": ai_data.get("Image_URL", ""),
                            "Recipe_URL": url_input
                        }])
                        
                        if df.empty or len(df.columns) == 0:
                            updated_df = new_row
                        else:
                            updated_df = pd.concat([df, new_row], ignore_index=True)
                        
                        conn.update(data=updated_df)
                        st.cache_data.clear()
                        st.success(f"המתכון '{ai_data.get('Recipe_Name', '')}' נוסף בהצלחה!")
                    except Exception as e:
                        st.error(f"שגיאה בשמירה למסד הנתונים: {e}")

with tab_board:
    st.header("המתכונים שלי")
    try:
        df = conn.read(ttl=0).fillna("")
        
        if df.empty or len(df.columns) == 0:
            st.info("לוח המתכונים כרגע ריק. הוסף את המתכון הראשון שלך בטאב השני.")
        else:
            categories = [c for c in df['Category'].unique() if c != ""]
            
            for cat in categories:
                st.subheader(cat)
                cat_df = df[df['Category'] == cat]
                
                cols = st.columns(4)
                for i, (index, row) in enumerate(cat_df.iterrows()):
                    col = cols[i % 4]
                    with col:
                        with st.container(border=True):
                            # תמונה
                            img_url = str(row.get('Image_URL', ''))
                            if img_url and img_url.startswith('http'):
                                st.image(img_url, use_column_width=True)
                            
                            # כותרת
                            recipe_name = row.get('Recipe_Name', '')
                            st.markdown(f"**{recipe_name if recipe_name else 'מתכון ללא שם'}**")
                            
                            # מצרכים
                            with st.expander("מצרכים"):
                                st.text(row.get('Ingredients', 'אין מצרכים זמינים'))
                            
                            # חלוקה לכפתור מחיקה וכפתור לינק
                            action_cols = st.columns([1, 2])
                            with action_cols[0]:
                                if st.button("🗑️", key=f"del_{index}", help="מחק מתכון זה"):
                                    confirm_delete(index)
                            with action_cols[1]:
                                st.markdown(f"[🔗 למתכון המלא]({row.get('Recipe_URL', '#')})")
                                
    except Exception as e:
        st.error(f"שגיאה בקריאת הנתונים מ-Google Sheets: {e}")
