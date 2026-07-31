import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="לוח מתכונים", page_icon="🍳", layout="wide")

def extract_recipe_data(url, category):
    try:
        # הוספנו User-Agent מלא כדי שהאתר לא יחשוב שאנחנו בוט פשוט
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=10)
        
        # שלב קריטי: הכרחת קידוד לעברית כדי למנוע ג'יבריש
        res.encoding = 'utf-8' 
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, 'html.parser')
        
        text_content = soup.get_text(separator='\n', strip=True)
        images = [img.get('src') for img in soup.find_all('img') if img.get('src') and img.get('src').startswith('http')]
        images_list = "\n".join(images[:15])
        
        # חילוץ מידע מובנה (Schema) אם קיים באתר (מאוד עוזר ל-AI באתרי מתכונים)
        structured_data = []
        for script in soup.find_all('script', type='application/ld+json'):
            if script.string:
                structured_data.append(script.string)
        structured_text = "\n".join(structured_data)
        
        genai.configure(api_key=st.secrets["AI_API_KEY"])
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if not available_models:
            st.error("לא נמצאו מודלים זמינים בחשבון.")
            return None
            
        prompt = f'''
        You are an advanced recipe data extractor. I will provide text and structured data from a recipe website, plus image URLs.
        Extract the recipe details and return ONLY a valid JSON object. Do not use Markdown formatting, just the raw JSON.
        If a field is missing, leave it as an empty string.
        
        Required JSON structure:
        {{
            "Recipe_Name": "The exact name of the recipe in Hebrew",
            "Ingredients": "The list of ingredients in Hebrew, separated by a newline character (\\n)",
            "Image_URL": "The best matching high-resolution image URL of the dish from the provided list"
        }}
        
        Structured Data (Metadata):
        {structured_text[:5000]}
        
        Website Text (partial):
        {text_content[:15000]}
        
        Potential Image URLs:
        {images_list}
        '''
        
        data = None
        preferred_models = ['models/gemini-3.1-pro', 'models/gemini-3.1-flash', 'models/gemini-3.0-pro', 'models/gemini-3.0-flash']
        models_to_try = [m for m in preferred_models if m in available_models] + [m for m in available_models if m not in preferred_models]
        
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                res_text = response.text.strip()
                
                if res_text.startswith("```json"):
                    res_text = res_text[7:-3].strip()
                elif res_text.startswith("```"):
                    res_text = res_text[3:-3].strip()
                    
                data = json.loads(res_text)
                break 
                
            except Exception:
                continue
                
        return data
        
    except Exception as e:
        st.error(f"שגיאה כללית בחילוץ: {e}")
        return None

st.title("🍳 לוח המתכונים")

conn = st.connection("gsheets", type=GSheetsConnection)
tab_board, tab_add = st.tabs(["📋 לוח מתכונים", "➕ הוספת מתכון חדש"])

with tab_add:
    st.header("הזנת מתכון חדש")
    with st.form("add_recipe"):
        url_input = st.text_input("הכנס לינק למתכון:")
        category_input = st.selectbox("קטגוריה:", ["בשר", "עוף", "דגים", "חלבי", "צמחוני", "טבעוני", "מאפים", "קינוחים", "שונות"])
        submit = st.form_submit_button("חלץ ושמור מתכון")
        
        if submit and url_input:
            with st.spinner("מנתח את העמוד ומחלץ נתונים..."):
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
        # קריאת הנתונים ומילוי שדות ריקים בטקסט ריק כדי למנוע הופעה של 'nan'
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
                            
                            # כותרת (עם גיבוי למקרה שאין שם)
                            recipe_name = row.get('Recipe_Name', '')
                            st.markdown(f"**{recipe_name if recipe_name else 'מתכון ללא שם'}**")
                            
                            # מצרכים
                            with st.expander("מצרכים"):
                                st.text(row.get('Ingredients', 'אין מצרכים זמינים'))
                            
                            # כפתורי פעולה בשורה אחת
                            action_cols = st.columns([2, 1])
                            with action_cols[0]:
                                st.markdown(f"[🔗 למתכון המלא]({row.get('Recipe_URL', '#')})")
                            with action_cols[1]:
                                # כפתור מחיקה - משתמש באינדקס של השורה
                                if st.button("🗑️", key=f"del_{index}", help="מחק מתכון זה"):
                                    # קריאה מחדש של הנתונים כדי למנוע התנגשויות
                                    fresh_df = conn.read(ttl=0)
                                    # מחיקת השורה לפי האינדקס
                                    fresh_df = fresh_df.drop(index)
                                    # עדכון הגיליון
                                    conn.update(data=fresh_df)
                                    # ניקוי זיכרון מטמון ורענון העמוד
                                    st.cache_data.clear()
                                    st.rerun()
                                    
    except Exception as e:
        st.error(f"שגיאה בקריאת הנתונים: {e}")
