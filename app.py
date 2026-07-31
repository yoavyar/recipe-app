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
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        
        text_content = soup.get_text(separator='\n', strip=True)
        images = [img.get('src') for img in soup.find_all('img') if img.get('src') and img.get('src').startswith('http')]
        images_list = "\n".join(images[:15])
        
        genai.configure(api_key=st.secrets["AI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        
        prompt = f'''
        You are an advanced recipe data extractor. I will provide text from a recipe website and a list of image URLs found on the page.
        Extract the recipe details and return ONLY a valid JSON object. Do not use Markdown formatting (like ```json), just return the raw JSON string.
        
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
        
        response = model.generate_content(prompt)
        res_text = response.text.strip()
        
        if res_text.startswith("```json"):
            res_text = res_text[7:-3].strip()
        elif res_text.startswith("```"):
            res_text = res_text[3:-3].strip()
            
        data = json.loads(res_text)
        return data
        
    except Exception as e:
        st.error(f"שגיאה בחילוץ הנתונים: {e}")
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
                            "Recipe_Name": ai_data.get("Recipe_Name", "ללא שם"),
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
                        st.success(f"המתכון '{ai_data.get('Recipe_Name', '')}' נוסף בהצלחה לגיליון!")
                    except Exception as e:
                        st.error(f"שגיאה בשמירה למסד הנתונים: {e}")

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
                
                cols = st.columns(4)
                for i, (_, row) in enumerate(cat_df.iterrows()):
                    col = cols[i % 4]
                    with col:
                        with st.container(border=True):
                            if pd.notna(row.get('Image_URL')) and row['Image_URL']:
                                st.image(row['Image_URL'], use_column_width=True)
                            st.markdown(f"**{row.get('Recipe_Name', 'ללא שם')}**")
                            with st.expander("מצרכים"):
                                st.text(row.get('Ingredients', ''))
                            st.markdown(f"[🔗 למעבר למתכון המלא]({row.get('Recipe_URL', '#')})")
    except Exception as e:
        st.error(f"שגיאה בקריאת הנתונים מ-Google Sheets: {e}")
