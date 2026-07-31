import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import json
from streamlit_gsheets import GSheetsConnection

# הגדרות תצוגה
st.set_page_config(page_title="לוח מתכונים", page_icon="🍳", layout="wide")

# --- מנגנון ה-AI לחילוץ הנתונים (מעודכן לגישת REST API ישירה) ---
def extract_recipe_data(url, category):
    try:
        # 1. משיכת תוכן ה-HTML של המתכון
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # חילוץ הטקסט הקיים בעמוד
        text_content = soup.get_text(separator='\n', strip=True)
        
        # חילוץ תמונות (ניתן למודל לבחור את התמונה הרלוונטית ביותר)
        images = [img.get('src') for img in soup.find_all('img') if img.get('src') and img.get('src').startswith('http')]
        images_list = "\n".join(images[:15])
        
        # 2. קריאה ישירה ל-API של Gemini (עוקף את ספריית הפייתון)
        api_key = st.secrets["AI_API_KEY"]
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        
        prompt = f'''
        You are an advanced recipe data extractor. I will provide text from a recipe website and a list of image URLs found on the page.
        Extract the recipe details.
        
        Required JSON structure:
        {{
            "Recipe_Name": "The exact name of the recipe in Hebrew",
            "Ingredients": "The list of ingredients in Hebrew, separated by a newline character (\\n)",
            "Image_URL": "The best matching high-resolution image URL of the dish from the provided list"
        }}
        
        Website Text (partial):
        {text_content[:15000]}
        
        Potential Image URLs:
        {images_list}
        '''
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json" # מכריח את המודל להחזיר JSON חוקי ונקי
            }
        }
        
        # שליחת הבקשה
        response = requests.post(api_url, headers={'Content-Type': 'application/json'}, json=payload)
        
        if not response.ok:
            st.error(f"שגיאת שרת מול מודל ה-AI: {response.status_code} - {response.text}")
            return None
            
        res_data = response.json()
        res_text = res_data['candidates'][0]['content']['parts'][0]['text']
        
        data = json.loads(res_text)
        return data
        
    except Exception as e:
        st.error(f"שגיאה בחילוץ הנתונים: {e}")
        return None


# --- ממשק המשתמש ---
st.title("🍳 לוח המתכונים")

# יצירת אובייקט חיבור ל-Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

tab_board, tab_add = st.tabs(["📋 לוח מתכונים", "➕ הוספת מתכון חדש"])

# --- טאב הזנה ---
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
                        # קריאת כלל הנתונים הקיימים (ttl=0 מונע קאש)
                        df = conn.read(ttl=0)
                        
                        # יצירת שורה חדשה
                        new_row = pd.DataFrame([{
                            "Category": category_input,
                            "Recipe_Name": ai_data.get("Recipe_Name", "ללא שם"),
                            "Ingredients": ai_data.get("Ingredients", ""),
                            "Image_URL": ai_data.get("Image_URL", ""),
                            "Recipe_URL": url_input
                        }])
                        
                        # חיבור השורה ל-DataFrame הקיים ושמירה
                        if df.empty or len(df.columns) == 0:
                            updated_df = new_row
                        else:
                            updated_df = pd.concat([df, new_row], ignore_index=True)
                        
                        conn.update(data=updated_df)
                        
                        # ניקוי Cache של Streamlit
                        st.cache_data.clear()
                        st.success(f"המתכון '{ai_data.get('Recipe_Name', '')}' נוסף בהצלחה לגיליון!")
                    except Exception as e:
                        st.error(f"שגיאה בשמירה למסד הנתונים: {e}")

# --- טאב לוח תצוגה ---
with tab_board:
    st.header("המתכונים שלי")
    try:
        df = conn.read(ttl=0)
        
        if df.empty or len(df.columns) == 0:
            st.info("לוח המתכונים כרגע ריק. הוסף את המתכון הראשון שלך בטאב השני.")
        else:
            categories = df['Category'].dropna().unique()
            
            for cat in categories:
                st.subheader(cat)
                cat_df = df[df['Category'] == cat]
                
                # חלוקה ל-4 עמודות ליצירת Grid (כרטיסיות)
                cols = st.columns(4)
                for i, (_, row) in enumerate(cat_df.iterrows()):
                    col = cols[i % 4]
                    with col:
                        with st.container(border=True):
                            # תמונה
                            if pd.notna(row.get('Image_URL')) and row['Image_URL']:
                                st.image(row['Image_URL'], use_column_width=True)
                            
                            # כותרת המתכון
                            st.markdown(f"**{row.get('Recipe_Name', 'ללא שם')}**")
                            
                            # מצרכים (תחת Expander כדי לא להעמיס על התצוגה)
                            with st.expander("מצרכים"):
                                st.text(row.get('Ingredients', ''))
                            
                            # לינק למקור
                            st.markdown(f"[🔗 למעבר למתכון המלא]({row.get('Recipe_URL', '#')})")
    except Exception as e:
        st.error(f"שגיאה בקריאת הנתונים מ-Google Sheets: {e}")
