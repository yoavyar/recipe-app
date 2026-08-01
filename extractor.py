import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import json
import re
import instaloader

def extract_recipe_data(url, category, api_key):
    text_content = ""
    images_list = ""
    meta_title = ""
    meta_image = ""

    try:
        # בדיקה האם מדובר בלינק של אינסטגרם
        if "instagram.com" in url:
            L = instaloader.Instaloader()
            # חילוץ ה"קוד" של הפוסט מתוך הלינק
            match = re.search(r'(p|reel)/([^/?#&]+)', url)
            if match:
                shortcode = match.group(2)
                try:
                    # הורדת המידע מאינסטגרם
                    post = instaloader.Post.from_shortcode(L.context, shortcode)
                    text_content = post.caption if post.caption else ""
                    meta_image = post.url
                    images_list = meta_image
                except Exception as e:
                    return {"error": f"שגיאה בקריאת הפוסט מאינסטגרם (ייתכן שהפוסט פרטי או שיש חסימה): {e}"}
            else:
                 return {"error": "לינק אינסטגרם לא תקין או לא מזוהה."}
                 
        # אם זה לינק רגיל של אתר (כמו Mako, שף לבן וכו')
        else:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"
            }
            res = requests.get(url, headers=headers, timeout=15)
            res.encoding = 'utf-8'
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, 'html.parser')
            
            mt = soup.find('meta', property='og:title')
            meta_title = mt['content'] if mt else ""
            
            mi = soup.find('meta', property='og:image')
            meta_image = mi['content'] if mi else ""
            
            text_content = soup.get_text(separator='\n', strip=True)
            images = [img.get('src') for img in soup.find_all('img') if img.get('src') and img.get('src').startswith('http')]
            
            if meta_image and meta_image not in images:
                images.insert(0, meta_image)
                
            images_list = "\n".join(images[:15])

        # --- שלב קריאת ה-AI לכל סוגי הלינקים ---
        genai.configure(api_key=api_key)
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if not available_models:
            return {"error": "לא נמצאו מודלים זמינים בחשבון."}
            
        prompt = f'''
        You are an advanced recipe data extractor. 
        Extract the recipe details into a strictly valid JSON object.
        
        Required JSON structure:
        {{
            "Recipe_Name": "The exact name of the recipe in Hebrew",
            "Ingredients": "The list of ingredients in Hebrew, separated by a newline character (\\n)",
            "Image_URL": "The best matching high-resolution image URL"
        }}
        
        Metadata Title: {meta_title}
        Metadata Image: {meta_image}
        
        Website Text (partial):
        {text_content[:15000]}
        
        Potential Image URLs:
        {images_list}
        
        Instructions: 
        1. Try to use the Metadata Title for "Recipe_Name" if available. If it's an Instagram post and there is no title, generate a fitting short Hebrew name based on the text.
        2. Use the Metadata Image for "Image_URL" if available.
        3. Extract ingredients from the text. If missing, estimate them based on the name.
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
                
        if data is None:
            return {"error": "אף מודל לא הצליח להשלים את הבקשה. ייתכן שהטקסט באתר/בפוסט אינו קריא."}
            
        return data
        
    except Exception as e:
        return {"error": f"שגיאה כללית בחילוץ: {e}"}
