# מעבר ל-CUTROOM AI Director 5.6.1

מומלץ לחלץ את v5.6.1 לתיקייה חדשה ולא לדרוס התקנה קודמת.

אם יש פרויקטים חשובים, העתק רק את `data/projects/` ואת `data/exports/` לפי הצורך. אל תעתיק `.venv`, `.tools`, `.setup-complete`, `server.py`, `cutroom/`, `web/`, `config.json` או סקריפטי התקנה מגרסה ישנה.

ב-5.4 נוספו נתוני `pre_analysis.audio`, הגדרת `silence_threshold_dbfs` ו-`burn_captions`. פרויקט ישן שאין בו את השדות האלה עדיין נפתח; CUTROOM משתמשת בברירות המחדל החדשות כאשר הם חסרים.

ב-5.5 נוספו Story Beats, זיהוי Facecam יציב יותר למסלול Reel, נתיבי תמלול עברית משופרים ומודלי Director מדורגים לפי מצב ביצועים. אין להעתיק `config.json` ישן אם רוצים את ברירות המחדל החדשות.

ב־5.6 Short/Podcast סמנטי דורש Story AI אמיתי. אין יותר fallback שקט ל-Ranking. בפעם הראשונה ייתכן ש-CUTROOM תכין את Qwen המקומי לפני יצירת Draft. סיכומי Chapters ו-Global Outline נשמרים ב-Cache כדי ש-Refine ושינוי יעד יהיו קלים יותר.
