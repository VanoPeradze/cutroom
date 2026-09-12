const en = {
  skip: "Skip to content", saved: "Saved", projects: "Projects", language: "Language", advanced: "Advanced", studio: "Studio", studioWorkspaceTitle: "Your creative workspace", backToDirector: "Project overview", studioNeedsDraft: "Create a first edit before opening Studio.", render: "Export",
  welcomeBadge: "YOUR LOCAL WORKSPACE", welcomeTitle: "What will you create today?", welcomeLead: "Start with your footage. Let Director build a first cut, then make it yours in the editor.", newProject: "Create project", recent: "Your projects", localMode: "Runs locally", privateWorkspace: "Your footage stays on this computer", trustOpen: "Free & open source", trustLocal: "Local-first processing", trustFormats: "Reels & YouTube",
  stepFootage: "Preparation", stepBrief: "Director", stepDraft: "Draft", director: "AI Director", setupTitle: "What are we editing today?", setupHelp: "Add one or two sources. With two, choose the screen, camera and audio before Director starts.",
  addMain: "Add main recording", dropVideo: "Click or drop a video", autoSync: "Automatic sync", addSecond: "Add second recording", optionalCamera: "Optional — camera, screen or second angle", uploadLimit: "Up to {size} per video", fileTooLarge: "This video is {file}. The maximum allowed size is {limit}.", notEnoughDisk: "Not enough free disk space. This video is {file}; only {free} is currently free.", localUploadInterrupted: "The upload to CUTROOM's local server was interrupted. The file-size check passed, so this is not a size-limit error.",
  resultType: "What is the result?", editStyleTitle: "Choose an edit style", editStyleHelp: "Choose the editing rhythm. Your goal, output format and target length stay under your control.", editStyleEvidence: "Presets currently use transcript, audio and pacing; visual gameplay-event detection will be added later.", short: "Short / Reel", podcastClip: "Conversation clip", speakerFocus: "Speaker focus", cleanCut: "Full clean-up", keepOriginal: "Preserve structure",
  targetLength: "Target length", pace: "Pace", gentle: "Natural", balanced: "Balanced", dynamic: "Fast", balancedHelp: "Removes clear repetition and pauses without making speech mechanical.",
  directionNote: "Direction for Director", instructionPlaceholder: "Example: keep the pricing explanation and open with the result.", waitingForVideo: "Waiting for the main recording", makeEdit: "Make my edit", oneDraft: "One main edit plus ranked Reel options from the same analysis",
  directorWorking: "Director is working", listening: "Listening to the footage", directorPreparing: "Preparing your edit", preparingAI: "Preparing the AI engine", taskListen: "Transcription and language", taskStory: "Retakes, ideas and strong moments", taskSync: "Synchronization and framing", taskDraft: "Building a coherent edit", cancel: "Cancel", retry: "Try again", backToSettings: "Back to settings",
  firstDraft: "First edit", beforeAfter: "Before / after", whatChanged: "What changed", adjust: "Refine the edit", oneClick: "One click", anotherCut: "Try another cut", anotherCutReady: "A different quality-ranked cut is ready", shorter: "Shorter", keepMore: "Keep more", moreEnergy: "More energy", fewerSwitches: "Fewer switches", focusSpeaker: "Focus speaker", renderFinal: "Export video", changeBrief: "Change target or pace", restart: "Restart",
  precisionTools: "Precision tools", timeline: "Timeline", framing: "Framing", transcript: "Transcript", settings: "Settings", fit: "Fit", kept: "Kept", removed: "Removed", cameraSwitch: "Camera", timelineHelp: "Click to move the playhead. Red ranges are not included in the output.",
  layout: "Layout", auto: "Automatic", stacked: "Stacked", sideBySide: "Side by side", embeddedCamera: "Screen + embedded camera", horizontalFocus: "Horizontal focus", verticalFocus: "Vertical focus", zoom: "Zoom", resetFraming: "Reset framing", cameraFound: "Camera window found", cameraFoundHelp: "A stable face area was found. Confirm it before using this composition.", useLayout: "Use layout",
  searchTranscript: "Search transcript", aspect: "Aspect ratio", resolution: "Resolution", quality: "Export quality", fast: "Fast", highQuality: "High", autoReframe: "Automatic framing", autoReframeHelp: "Uses the detected speaker center", captions: "Captions", captionsHelp: "Keeps a synchronized transcript for export", checkingAI: "Checking AI engines", installModel: "Install model", sourceRatio: "Source",
  export: "Export", readyToExport: "Ready to export?", exportHelp: "Export uses the original full-quality files, not a proxy.", startExport: "Start export", downloadVideo: "Download video",
  ready: "Ready to create the first edit", uploadFailed: "Upload failed", directorFailed: "Director could not finish", exportFailed: "Export failed", aiReady: "AI engines ready", aiPartial: "The deterministic editor works; install the language model for deeper story decisions", noProjects: "No projects yet", delete: "Delete",
  decision_duration: "Duration tightened", decision_dead_air: "Long pauses removed", decision_retakes: "Retakes removed", decision_repetitions: "Repeated ideas removed", decision_fillers: "Filler openings cleaned", decision_low_value: "Low-value detours removed", decision_manual: "Manual cuts preserved", decision_sync: "Two recordings synchronized",
  secondsRemoved: "seconds removed", occurrences: "occurrences", syncOffset: "offset", sourceA: "Source A", sourceB: "Source B", draftReady: "Your first edit is ready", preparing: "Preparing source", projectCreated: "Project created", modelMissing: "Editor model is not installed", installRecommended: "Install recommended AI model"
};

const he = {
  ...en,
  skip: "דלג לתוכן", saved: "נשמר", projects: "פרויקטים", language: "שפה", advanced: "מתקדם", studio: "Studio", studioWorkspaceTitle: "עריכה מדויקת, באותו מסך", backToDirector: "חזרה ל־Director", studioNeedsDraft: "צריך ליצור עריכה ראשונה לפני פתיחת Studio.", render: "ייצוא",
  welcomeBadge: "עורך וידאו AI מקומי", welcomeTitle: "העריכה הראשונה שלך, בלי להתחיל מאפס.", welcomeLead: "מכניסים צילום אחד או שניים. CUTROOM מתמלל, מסנכרן, מוצא את הרגעים החזקים ובונה Draft שאפשר לדייק ולייצא.", newProject: "צור פרויקט חדש", recent: "פרויקטים אחרונים", localMode: "עובד מקומית", privateWorkspace: "חומר הגלם נשאר במחשב שלך", trustOpen: "חינמי וקוד פתוח", trustLocal: "עיבוד מקומי", trustFormats: "Reels ו־YouTube",
  stepFootage: "הכנה", stepBrief: "Director", stepDraft: "Draft", director: "AI Director", setupTitle: "מה אנחנו עורכים היום?", setupHelp: "העלו מקור אחד או שניים. עם שני מקורות בוחרים מסך, מצלמה וקול לפני שה־Director מתחיל.",
  addMain: "הוסף צילום ראשי", dropVideo: "לחיצה או גרירת וידאו", autoSync: "סנכרון אוטומטי", addSecond: "הוסף צילום נוסף", optionalCamera: "אופציונלי — מצלמה, מסך או זווית שנייה", uploadLimit: "עד {size} לסרטון", fileTooLarge: "הסרטון שוקל {file}. המשקל המקסימלי הוא {limit}.", notEnoughDisk: "אין מספיק מקום פנוי בדיסק. הסרטון שוקל {file}, וכרגע פנויים {free}.", localUploadInterrupted: "ההעלאה לשרת המקומי של CUTROOM נקטעה. בדיקת המשקל עברה, לכן זו אינה שגיאת מגבלת משקל.",
  resultType: "מה התוצאה?", editStyleTitle: "בחר סגנון עריכה", editStyleHelp: "לחיצה אחת מכוונת את הקצב, האורך, המסגור וה־Storyline. אפשר לדייק הכול אחר כך.", editStyleEvidence: "הסגנונות כרגע משתמשים בתמלול, סאונד וקצב; זיהוי אירועי משחק חזותיים יתווסף בהמשך.", short: "Short / Reel", podcastClip: "קטע שיחה", speakerFocus: "פוקוס דובר", cleanCut: "ניקוי מלא", keepOriginal: "שומר את המבנה",
  targetLength: "אורך יעד", pace: "קצב", gentle: "טבעי", balanced: "מאוזן", dynamic: "מהיר", balancedHelp: "מסיר חזרות והפסקות ברורות, בלי להפוך את הדיבור למכני.",
  directionNote: "הנחיה ל־Director", instructionPlaceholder: "לדוגמה: שמור את ההסבר על המחיר ותתחיל מהתוצאה.", waitingForVideo: "ממתין לצילום הראשי", makeEdit: "צור לי עריכה", oneDraft: "עריכה ראשית ועוד חלופות Reel מאותו ניתוח",
  directorWorking: "ה־Director עובד", listening: "מקשיב לחומר הגלם", directorPreparing: "מכין את העריכה שלך", preparingAI: "מכין את מנוע ה־AI", taskListen: "תמלול והבנת שפה", taskStory: "חזרות, רעיונות ורגעים חזקים", taskSync: "סנכרון ומסגור", taskDraft: "בניית עריכה קוהרנטית", cancel: "ביטול", retry: "נסה שוב", backToSettings: "חזרה להגדרות",
  firstDraft: "העריכה הראשונה", beforeAfter: "לפני / אחרי", whatChanged: "מה השתנה", adjust: "דייק את העריכה", oneClick: "בלחיצה", shorter: "קצר יותר", keepMore: "שמור יותר", moreEnergy: "יותר אנרגיה", fewerSwitches: "פחות החלפות", focusSpeaker: "פוקוס על הדובר", renderFinal: "ייצא את הסרטון", changeBrief: "שנה יעד או קצב", restart: "מהתחלה",
  precisionTools: "כלי דיוק", timeline: "Timeline", framing: "מסגור", transcript: "תמלול", settings: "הגדרות", fit: "התאם", kept: "נשאר", removed: "הוסר", cameraSwitch: "מצלמה", timelineHelp: "לחיצה מזיזה את ה־Playhead. החלקים האדומים אינם מופיעים בפלט.",
  layout: "פריסה", auto: "אוטומטי", stacked: "אחד מעל השני", sideBySide: "זה לצד זה", embeddedCamera: "מסך + מצלמה פנימית", horizontalFocus: "מוקד אופקי", verticalFocus: "מוקד אנכי", zoom: "זום", resetFraming: "אפס מסגור", cameraFound: "נמצא חלון מצלמה", cameraFoundHelp: "המערכת מצאה אזור פנים קבוע. יש לאשר אותו לפני שימוש.", useLayout: "השתמש בפריסה",
  searchTranscript: "חיפוש בתמלול", aspect: "יחס מסך", resolution: "רזולוציה", quality: "איכות יצוא", fast: "מהיר", highQuality: "גבוהה", autoReframe: "מסגור אוטומטי", autoReframeHelp: "משתמש במרכז הדובר שנמצא", captions: "כתוביות", captionsHelp: "שומר תמלול מסונכרן לייצוא", checkingAI: "בודק מנועי AI", installModel: "התקן מודל", sourceRatio: "מקור",
  export: "ייצוא", readyToExport: "מוכן לייצא?", exportHelp: "הייצוא משתמש בקובצי המקור המלאים, לא ב־Proxy.", startExport: "התחל יצוא", downloadVideo: "הורד סרטון",
  ready: "מוכן ליצור את העריכה הראשונה", uploadFailed: "העלאת הקובץ נכשלה", directorFailed: "ה־Director לא הצליח לסיים", exportFailed: "הייצוא נכשל", aiReady: "מנועי ה־AI מוכנים", aiPartial: "מנוע העריכה המקומי עובד; התקנת מודל שפה תוסיף הבנת סיפור עמוקה יותר", noProjects: "עדיין אין פרויקטים", delete: "מחק",
  decision_duration: "האורך הודק", decision_dead_air: "הפסקות ארוכות הוסרו", decision_retakes: "טייקים חוזרים הוסרו", decision_repetitions: "רעיונות שחזרו הוסרו", decision_fillers: "פתיחות עם מילות מילוי נוקו", decision_low_value: "סטיות חלשות הוסרו", decision_manual: "חיתוכים ידניים נשמרו", decision_sync: "שני הצילומים סונכרנו",
  secondsRemoved: "שניות הוסרו", occurrences: "מקרים", syncOffset: "היסט", sourceA: "צילום A", sourceB: "צילום B", draftReady: "העריכה הראשונה מוכנה", preparing: "מכין את המקור", projectCreated: "הפרויקט נוצר", modelMissing: "מודל העריכה אינו מותקן", installRecommended: "התקן מודל AI מומלץ"
};

const ar = {
  ...en,
  skip: "تجاوز إلى المحتوى", saved: "تم الحفظ", projects: "المشاريع", language: "اللغة", advanced: "متقدم", studio: "Studio", studioWorkspaceTitle: "تحرير دقيق في مساحة عمل واحدة", backToDirector: "العودة إلى Director", studioNeedsDraft: "أنشئ مسودة أولى قبل فتح Studio.", render: "تصدير",
  welcomeTitle: "حوّل اللقطات الخام إلى مونتاج أول.", welcomeLead: "أضف تسجيلاً واحداً أو اثنين. يستمع المخرج، يزامن، يختار أقوى المقاطع ويعيد مسودة جاهزة للتحسين.", newProject: "مشروع جديد", recent: "الأخيرة",
  stepFootage: "اللقطات", stepBrief: "النتيجة", stepDraft: "المونتاج", setupTitle: "ماذا نحرر اليوم؟", setupHelp: "أضف مصدراً واحداً أو مصدرين. مع مصدرين اختر الشاشة والكاميرا والصوت قبل بدء Director.",
  addMain: "أضف التسجيل الرئيسي", dropVideo: "انقر أو اسحب فيديو", autoSync: "مزامنة تلقائية", addSecond: "أضف تسجيلاً ثانياً", optionalCamera: "اختياري — كاميرا أو شاشة أو زاوية ثانية", uploadLimit: "حتى {size} لكل فيديو", fileTooLarge: "حجم هذا الفيديو {file}. الحد الأقصى المسموح هو {limit}.", notEnoughDisk: "لا توجد مساحة قرص كافية. حجم الفيديو {file} والمتاح حالياً {free}.", localUploadInterrupted: "انقطع الرفع إلى خادم CUTROOM المحلي. اجتاز الملف فحص الحجم، لذا فهذه ليست مشكلة حد الحجم.",
  resultType: "ما هي النتيجة؟", podcastClip: "مقطع حوار", speakerFocus: "تركيز على المتحدث", cleanCut: "تنظيف كامل", keepOriginal: "يحافظ على البنية", targetLength: "المدة المستهدفة", pace: "الإيقاع", gentle: "طبيعي", balanced: "متوازن", dynamic: "سريع",
  directionNote: "تعليمات للمخرج", instructionPlaceholder: "مثال: احتفظ بشرح السعر وابدأ بالنتيجة.", waitingForVideo: "بانتظار التسجيل الرئيسي", makeEdit: "أنشئ المونتاج", oneDraft: "مونتاج رئيسي وخيارات Reel مرتبة من التحليل نفسه",
  directorWorking: "المخرج يعمل", listening: "يستمع إلى اللقطات", directorPreparing: "يجهز المونتاج", preparingAI: "يجهز محرك الذكاء الاصطناعي", firstDraft: "المونتاج الأول", whatChanged: "ما الذي تغير", adjust: "حسّن المونتاج", shorter: "أقصر", keepMore: "احتفظ بالمزيد", moreEnergy: "طاقة أكبر", fewerSwitches: "تبديلات أقل", focusSpeaker: "ركز على المتحدث", renderFinal: "صدّر الفيديو", changeBrief: "غيّر الهدف أو الإيقاع",
  precisionTools: "أدوات الدقة", framing: "التأطير", transcript: "النص", settings: "الإعدادات", layout: "التخطيط", auto: "تلقائي", stacked: "واحد فوق الآخر", sideBySide: "جنباً إلى جنب", embeddedCamera: "شاشة + كاميرا مدمجة", searchTranscript: "ابحث في النص", aspect: "نسبة العرض", resolution: "الدقة", quality: "جودة التصدير", fast: "سريع", highQuality: "عالية", cancel: "إلغاء", startExport: "ابدأ التصدير", downloadVideo: "نزّل الفيديو"
};

const es = {
  ...en,
  skip: "Saltar al contenido", saved: "Guardado", projects: "Proyectos", language: "Idioma", advanced: "Avanzado", studio: "Studio", studioWorkspaceTitle: "Edición precisa en un solo espacio", backToDirector: "Volver a Director", studioNeedsDraft: "Crea un primer montaje antes de abrir Studio.", render: "Exportar",
  welcomeTitle: "Convierte el material bruto en un primer montaje.", welcomeLead: "Añade una o dos grabaciones. Director escucha, sincroniza, selecciona lo más fuerte y devuelve un borrador listo para publicar o ajustar.", newProject: "Proyecto nuevo", recent: "Recientes",
  stepFootage: "Material", stepBrief: "Qué crear", stepDraft: "El montaje", setupTitle: "¿Qué editamos hoy?", setupHelp: "Añade una o dos fuentes. Con dos, elige pantalla, cámara y audio antes de iniciar Director.",
  addMain: "Añadir grabación principal", dropVideo: "Haz clic o arrastra un vídeo", autoSync: "Sincronización automática", addSecond: "Añadir segunda grabación", optionalCamera: "Opcional — cámara, pantalla o segundo ángulo", uploadLimit: "Hasta {size} por vídeo", fileTooLarge: "Este vídeo ocupa {file}. El máximo permitido es {limit}.", notEnoughDisk: "No hay suficiente espacio libre. El vídeo ocupa {file} y hay {free} disponibles.", localUploadInterrupted: "La carga al servidor local de CUTROOM se interrumpió. La comprobación de tamaño pasó, así que no es un error de límite de tamaño.",
  resultType: "¿Cuál es el resultado?", podcastClip: "Clip de conversación", speakerFocus: "Enfoque en el hablante", cleanCut: "Limpieza completa", keepOriginal: "Conserva la estructura", targetLength: "Duración objetivo", pace: "Ritmo", gentle: "Natural", balanced: "Equilibrado", dynamic: "Rápido",
  directionNote: "Instrucción para Director", instructionPlaceholder: "Ejemplo: conserva la explicación del precio y abre con el resultado.", waitingForVideo: "Esperando la grabación principal", makeEdit: "Crear mi montaje", oneDraft: "Un montaje principal y opciones Reel del mismo análisis",
  directorWorking: "Director está trabajando", listening: "Escuchando el material", directorPreparing: "Preparando tu montaje", preparingAI: "Preparando el motor de IA", firstDraft: "Primer montaje", whatChanged: "Qué cambió", adjust: "Ajustar el montaje", shorter: "Más corto", keepMore: "Conservar más", moreEnergy: "Más energía", fewerSwitches: "Menos cambios", focusSpeaker: "Enfocar al hablante", renderFinal: "Exportar vídeo", changeBrief: "Cambiar objetivo o ritmo",
  precisionTools: "Herramientas de precisión", framing: "Encuadre", transcript: "Transcripción", settings: "Ajustes", layout: "Diseño", auto: "Automático", stacked: "Apilado", sideBySide: "Lado a lado", embeddedCamera: "Pantalla + cámara integrada", searchTranscript: "Buscar en la transcripción", aspect: "Relación de aspecto", resolution: "Resolución", quality: "Calidad de exportación", fast: "Rápida", highQuality: "Alta", cancel: "Cancelar", startExport: "Iniciar exportación", downloadVideo: "Descargar vídeo"
};

const fr = {
  ...en,
  skip: "Aller au contenu", saved: "Enregistré", projects: "Projets", language: "Langue", advanced: "Avancé", studio: "Studio", studioWorkspaceTitle: "Montage précis dans un seul espace", backToDirector: "Retour à Director", studioNeedsDraft: "Créez un premier montage avant d’ouvrir Studio.", render: "Exporter",
  welcomeTitle: "Transformez les rushes en premier montage.", welcomeLead: "Ajoutez un ou deux enregistrements. Director écoute, synchronise, sélectionne les passages forts et renvoie un montage prêt à publier ou affiner.", newProject: "Nouveau projet", recent: "Récents",
  stepFootage: "Rushes", stepBrief: "Résultat", stepDraft: "Montage", setupTitle: "Que montons-nous aujourd’hui ?", setupHelp: "Ajoutez une ou deux sources. Avec deux sources, choisissez écran, caméra et audio avant de lancer Director.",
  addMain: "Ajouter l’enregistrement principal", dropVideo: "Cliquez ou déposez une vidéo", autoSync: "Synchronisation automatique", addSecond: "Ajouter un second enregistrement", optionalCamera: "Facultatif — caméra, écran ou second angle", uploadLimit: "Jusqu’à {size} par vidéo", fileTooLarge: "Cette vidéo pèse {file}. La taille maximale est {limit}.", notEnoughDisk: "Espace disque insuffisant. La vidéo pèse {file} et il reste {free} disponibles.", localUploadInterrupted: "L’envoi vers le serveur local CUTROOM a été interrompu. Le contrôle de taille a réussi : ce n’est pas une erreur de limite de taille.",
  resultType: "Quel résultat ?", podcastClip: "Extrait de conversation", speakerFocus: "Priorité à l’orateur", cleanCut: "Nettoyage complet", keepOriginal: "Conserve la structure", targetLength: "Durée cible", pace: "Rythme", gentle: "Naturel", balanced: "Équilibré", dynamic: "Rapide",
  directionNote: "Consigne pour Director", instructionPlaceholder: "Exemple : gardez l’explication du prix et commencez par le résultat.", waitingForVideo: "En attente de l’enregistrement principal", makeEdit: "Créer mon montage", oneDraft: "Un montage principal et des options Reel issues de la même analyse",
  directorWorking: "Director travaille", listening: "Écoute des rushes", directorPreparing: "Préparation de votre montage", preparingAI: "Préparation du moteur IA", firstDraft: "Premier montage", whatChanged: "Modifications", adjust: "Affiner le montage", shorter: "Plus court", keepMore: "Garder davantage", moreEnergy: "Plus d’énergie", fewerSwitches: "Moins de changements", focusSpeaker: "Centrer l’orateur", renderFinal: "Exporter la vidéo", changeBrief: "Modifier la cible ou le rythme",
  precisionTools: "Outils de précision", framing: "Cadrage", transcript: "Transcription", settings: "Réglages", layout: "Disposition", auto: "Automatique", stacked: "Superposé", sideBySide: "Côte à côte", embeddedCamera: "Écran + caméra intégrée", searchTranscript: "Rechercher dans la transcription", aspect: "Format", resolution: "Résolution", quality: "Qualité d’export", fast: "Rapide", highQuality: "Haute", cancel: "Annuler", startExport: "Lancer l’export", downloadVideo: "Télécharger la vidéo"
};

const ru = {
  ...en,
  skip: "Перейти к содержанию", saved: "Сохранено", projects: "Проекты", language: "Язык", advanced: "Расширенный", studio: "Studio", studioWorkspaceTitle: "Точная правка в одном рабочем пространстве", backToDirector: "Назад к Director", studioNeedsDraft: "Сначала создайте черновой монтаж, затем откройте Studio.", render: "Экспорт",
  welcomeTitle: "Превратите исходники в первый монтаж.", welcomeLead: "Добавьте одну или две записи. Director слушает, синхронизирует, выбирает сильные фрагменты и возвращает готовый черновик.", newProject: "Новый проект", recent: "Недавние",
  stepFootage: "Материал", stepBrief: "Результат", stepDraft: "Монтаж", setupTitle: "Что монтируем сегодня?", setupHelp: "Добавьте один или два источника. Для двух выберите экран, камеру и звук до запуска Director.",
  addMain: "Добавить основную запись", dropVideo: "Нажмите или перетащите видео", autoSync: "Автосинхронизация", addSecond: "Добавить вторую запись", optionalCamera: "Необязательно — камера, экран или второй ракурс", uploadLimit: "До {size} на видео", fileTooLarge: "Размер видео — {file}. Максимально допустимый размер — {limit}.", notEnoughDisk: "Недостаточно свободного места. Видео занимает {file}, свободно {free}.", localUploadInterrupted: "Загрузка на локальный сервер CUTROOM прервалась. Проверка размера пройдена, поэтому это не ошибка ограничения размера.",
  resultType: "Какой результат?", podcastClip: "Фрагмент разговора", speakerFocus: "Фокус на спикере", cleanCut: "Полная очистка", keepOriginal: "Сохраняет структуру", targetLength: "Целевая длина", pace: "Темп", gentle: "Естественный", balanced: "Сбалансированный", dynamic: "Быстрый",
  directionNote: "Указание для Director", instructionPlaceholder: "Например: сохраните объяснение цены и начните с результата.", waitingForVideo: "Ожидание основной записи", makeEdit: "Создать монтаж", oneDraft: "Основной монтаж и варианты Reel из того же анализа",
  directorWorking: "Director работает", listening: "Анализ материала", directorPreparing: "Подготовка монтажа", preparingAI: "Подготовка AI-движка", firstDraft: "Первый монтаж", whatChanged: "Что изменилось", adjust: "Уточнить монтаж", shorter: "Короче", keepMore: "Сохранить больше", moreEnergy: "Больше энергии", fewerSwitches: "Меньше переключений", focusSpeaker: "Фокус на спикере", renderFinal: "Экспортировать видео", changeBrief: "Изменить цель или темп",
  precisionTools: "Точные инструменты", framing: "Кадрирование", transcript: "Транскрипт", settings: "Настройки", layout: "Компоновка", auto: "Автоматически", stacked: "Друг над другом", sideBySide: "Рядом", embeddedCamera: "Экран + встроенная камера", searchTranscript: "Поиск в транскрипте", aspect: "Соотношение сторон", resolution: "Разрешение", quality: "Качество экспорта", fast: "Быстро", highQuality: "Высокое", cancel: "Отмена", startExport: "Начать экспорт", downloadVideo: "Скачать видео"
};


Object.assign(en, {
  audioCleanup: "Sound cleanup", audioNatural: "Natural", audioClean: "Clean", audioTight: "Tight",
  audioNaturalHelp: "Keeps natural pauses and makes only gentle level corrections.",
  audioCleanHelp: "Shortens clear silence and balances quiet or loud speech from measured audio.",
  audioTightHelp: "Shortens more dead air and applies stronger speech leveling for fast content.",
  spokenLanguage: "Spoken language", performanceMode: "Performance mode", liteMode: "Lite", qualityMode: "Quality", customizeAudio: "Customize sound cleanup",
  silenceAction: "Silence", keep: "Keep", shortenSilence: "Shorten", removeSilence: "Remove", silenceMinimum: "Handle silence longer than", silenceKeep: "Silence to keep", maxRemoval: "Maximum removal",
  quietSpeech: "Quiet speech", boost: "Boost", loudSpeech: "Loud speech", lower: "Lower", normalizeSpeech: "Final loudness balance", normalizeSpeechHelp: "Lightweight loudness normalization on export",
  decision_quiet_audio: "Quiet speech balanced", decision_loud_audio: "Loud speech balanced", decision_clipping: "Clipping peaks detected", decision_audio_profile: "Measured sound profile", noiseFloor: "noise", speechLevel: "voice",
  taskListen: "Measuring sound and speech", taskStory: "Understanding speech and content",
});
Object.assign(he, {
  audioCleanup: "ניקוי סאונד", audioNatural: "טבעי", audioClean: "נקי", audioTight: "מהודק",
  audioNaturalHelp: "שומר הפסקות טבעיות ומבצע תיקוני עוצמה עדינים בלבד.",
  audioCleanHelp: "מקצר שקט ברור ומאזן דיבור חלש או חזק לפי המדידה של הסרטון.",
  audioTightHelp: "מקצר יותר זמן מת ומאזן דיבור בצורה חזקה יותר לתוכן מהיר.",
  spokenLanguage: "שפת הדיבור", performanceMode: "מצב ביצועים", liteMode: "קל", qualityMode: "איכות", customizeAudio: "התאם ניקוי סאונד",
  silenceAction: "שקט", keep: "השאר", shortenSilence: "קצר", removeSilence: "הסר", silenceMinimum: "טפל בשקט מעל", silenceKeep: "כמה שקט להשאיר", maxRemoval: "מקסימום הסרה",
  quietSpeech: "דיבור חלש", boost: "הגבר", loudSpeech: "דיבור חזק", lower: "הנמך", normalizeSpeech: "איזון עוצמה סופי", normalizeSpeechHelp: "איזון Loudness קל בזמן הייצוא",
  decision_quiet_audio: "דיבור חלש הוגבר", decision_loud_audio: "דיבור חזק הונמך", decision_clipping: "נמצאו Peaks בעייתיים", decision_audio_profile: "פרופיל סאונד שנמדד", noiseFloor: "רעש", speechLevel: "דיבור",
  taskListen: "מדידת סאונד ותמלול", taskStory: "הבנת דיבור ותוכן",
});
Object.assign(ar, {
  audioCleanup: "تنظيف الصوت", audioNatural: "طبيعي", audioClean: "نظيف", audioTight: "مشدود",
  audioNaturalHelp: "يحافظ على الوقفات الطبيعية ويجري تصحيحات خفيفة لمستوى الصوت.", audioCleanHelp: "يختصر الصمت الواضح ويوازن الكلام الهادئ أو العالي حسب القياس.", audioTightHelp: "يختصر المزيد من الفراغ ويوازن الكلام بقوة أكبر للمحتوى السريع.",
  spokenLanguage: "لغة الكلام", performanceMode: "وضع الأداء", liteMode: "خفيف", qualityMode: "جودة", customizeAudio: "تخصيص تنظيف الصوت", silenceAction: "الصمت", keep: "احتفظ", shortenSilence: "اختصر", removeSilence: "احذف", silenceMinimum: "عالج الصمت الأطول من", silenceKeep: "الصمت المتبقي", maxRemoval: "الحد الأقصى للحذف", quietSpeech: "كلام هادئ", boost: "ارفع", loudSpeech: "كلام عالٍ", lower: "اخفض", normalizeSpeech: "موازنة نهائية للصوت", normalizeSpeechHelp: "موازنة خفيفة أثناء التصدير", decision_quiet_audio: "تمت موازنة الكلام الهادئ", decision_loud_audio: "تمت موازنة الكلام العالي", decision_clipping: "تم اكتشاف قمم مشوهة", taskListen: "قياس الصوت والكلام", taskStory: "فهم الكلام والمحتوى",
});
Object.assign(es, {
  audioCleanup: "Limpieza de audio", audioNatural: "Natural", audioClean: "Limpio", audioTight: "Ajustado", audioNaturalHelp: "Conserva pausas naturales y corrige el nivel suavemente.", audioCleanHelp: "Acorta silencios claros y equilibra voz baja o alta según la medición.", audioTightHelp: "Acorta más aire muerto y nivela la voz con más fuerza.", spokenLanguage: "Idioma hablado", performanceMode: "Modo de rendimiento", liteMode: "Ligero", qualityMode: "Calidad", customizeAudio: "Personalizar audio", silenceAction: "Silencio", keep: "Conservar", shortenSilence: "Acortar", removeSilence: "Eliminar", silenceMinimum: "Tratar silencios mayores de", silenceKeep: "Silencio a conservar", maxRemoval: "Máximo a eliminar", quietSpeech: "Voz baja", boost: "Subir", loudSpeech: "Voz alta", lower: "Bajar", normalizeSpeech: "Balance final de volumen", normalizeSpeechHelp: "Normalización ligera al exportar", decision_quiet_audio: "Voz baja equilibrada", decision_loud_audio: "Voz alta equilibrada", decision_clipping: "Picos de clipping detectados", taskListen: "Midiendo audio y voz", taskStory: "Entendiendo voz y contenido",
});
Object.assign(fr, {
  audioCleanup: "Nettoyage audio", audioNatural: "Naturel", audioClean: "Propre", audioTight: "Serré", audioNaturalHelp: "Conserve les pauses naturelles et corrige doucement le niveau.", audioCleanHelp: "Raccourcit les silences clairs et équilibre la voix faible ou forte selon la mesure.", audioTightHelp: "Raccourcit davantage les temps morts et nivelle plus fortement la voix.", spokenLanguage: "Langue parlée", performanceMode: "Mode performance", liteMode: "Léger", qualityMode: "Qualité", customizeAudio: "Personnaliser l’audio", silenceAction: "Silence", keep: "Garder", shortenSilence: "Raccourcir", removeSilence: "Supprimer", silenceMinimum: "Traiter les silences de plus de", silenceKeep: "Silence à garder", maxRemoval: "Suppression maximale", quietSpeech: "Voix faible", boost: "Augmenter", loudSpeech: "Voix forte", lower: "Réduire", normalizeSpeech: "Équilibre final du volume", normalizeSpeechHelp: "Normalisation légère à l’export", decision_quiet_audio: "Voix faible équilibrée", decision_loud_audio: "Voix forte équilibrée", decision_clipping: "Pics de saturation détectés", taskListen: "Mesure du son et de la parole", taskStory: "Compréhension de la parole et du contenu",
});
Object.assign(ru, {
  audioCleanup: "Очистка звука", audioNatural: "Естественно", audioClean: "Чисто", audioTight: "Плотно", audioNaturalHelp: "Сохраняет естественные паузы и мягко корректирует громкость.", audioCleanHelp: "Сокращает явную тишину и выравнивает тихую или громкую речь по измерениям.", audioTightHelp: "Сильнее сокращает паузы и выравнивает речь для быстрого контента.", spokenLanguage: "Язык речи", performanceMode: "Режим производительности", liteMode: "Лёгкий", qualityMode: "Качество", customizeAudio: "Настроить звук", silenceAction: "Тишина", keep: "Оставить", shortenSilence: "Сократить", removeSilence: "Удалить", silenceMinimum: "Обрабатывать тишину длиннее", silenceKeep: "Оставить тишины", maxRemoval: "Максимум удаления", quietSpeech: "Тихая речь", boost: "Усилить", loudSpeech: "Громкая речь", lower: "Уменьшить", normalizeSpeech: "Финальный баланс громкости", normalizeSpeechHelp: "Лёгкая нормализация при экспорте", decision_quiet_audio: "Тихая речь выровнена", decision_loud_audio: "Громкая речь выровнена", decision_clipping: "Обнаружены пики клиппинга", taskListen: "Измерение звука и речи", taskStory: "Понимание речи и содержания",
});


Object.assign(en, {
  shortPromise: "Coherent story · 9:16 · automatic framing", youtubePromise: "Preserves structure · removes long dead air",
  shortModeTitle: "CUTROOM builds the Short for you", shortModeText: "Director chooses the strongest moments, preserves context and respects the requested duration. Screen + Facecam is only suggested until you confirm it.",
  youtubeModeTitle: "YouTube cleanup, without changing your story", youtubeModeText: "Keeps the original order and framing. CUTROOM shortens measured dead air and balances speech without semantic cuts by default.",
  podcastModeTitle: "Conversation clip with speaker focus", podcastModeText: "Keeps complete ideas, removes dead air and uses the available camera angles without excessive switching.",
  cleanModeTitle: "Clean the recording, keep the structure", cleanModeText: "Conservative cleanup: long pauses and level problems are fixed while the original sequence stays intact.",
  editCharacter: "Edit character", editCharacterHelp: "Only change this if you want to override the smart defaults", timelineGesture: "Drag = scrub · Ctrl+wheel = zoom",
  decision_target_trim: "Target duration enforced", decision_smart_layout: "Screen + Facecam layout confirmed"
});
Object.assign(he, {
  shortPromise: "סיפור מהודק · 9:16 · מסגור אוטומטי", youtubePromise: "שומר את המבנה · מסיר שקט ארוך",
  shortModeTitle: "CUTROOM בונה את ה-Short בשבילך", shortModeText: "ה-Director בוחר את הרגעים החזקים, שומר Context ומכבד את זמן היעד. Screen + Facecam נשאר רק כהצעה עד לאישור שלך.",
  youtubeModeTitle: "ניקוי YouTube בלי לשנות את הסיפור", youtubeModeText: "הסדר והמסגור נשארים כמו במקור. CUTROOM מקצרת שקט שנמדד ומאזנת דיבור, בלי חיתוכי תוכן כברירת מחדל.",
  podcastModeTitle: "קטע שיחה עם פוקוס על הדובר", podcastModeText: "שומר רעיונות שלמים, מסיר זמן מת ומשתמש בזוויות הקיימות בלי להחליף מצלמה יותר מדי.",
  cleanModeTitle: "ניקוי של ההקלטה, בלי לשנות את המבנה", cleanModeText: "ניקוי שמרני: הפסקות ארוכות ובעיות עוצמה מטופלות, והרצף המקורי נשאר כפי שהוא.",
  editCharacter: "אופי העריכה", editCharacterHelp: "משנים רק אם רוצים לעקוף את ברירת המחדל החכמה", timelineGesture: "גרירה = Scrub · Ctrl+גלגלת = Zoom",
  decision_target_trim: "זמן היעד נאכף", decision_smart_layout: "פריסת מסך + מצלמה אושרה"
});
Object.assign(ar, {
  shortPromise: "قصة مركزة · 9:16 · تأطير تلقائي", youtubePromise: "يحافظ على البنية · يزيل الصمت الطويل",
  shortModeTitle: "CUTROOM يبني الـShort لك", shortModeText: "يختار Director أقوى اللحظات ويحافظ على السياق ويحترم المدة المطلوبة ويكتشف الشاشة + الكاميرا تلقائياً.",
  youtubeModeTitle: "تنظيف YouTube من دون تغيير القصة", youtubeModeText: "يحافظ على الترتيب والإطار الأصليين ويختصر الصمت المقاس ويوازن الكلام دون حذف دلالي افتراضياً.",
  podcastModeTitle: "مقطع حوار مع تركيز على المتحدث", podcastModeText: "يحافظ على الأفكار الكاملة ويزيل الفراغ ويستخدم الزوايا المتاحة بدون تبديل مفرط.",
  cleanModeTitle: "نظف التسجيل وحافظ على بنيته", cleanModeText: "تنظيف محافظ للصمت الطويل ومستويات الصوت مع إبقاء التسلسل الأصلي.",
  editCharacter: "طابع المونتاج", editCharacterHelp: "غيّره فقط لتجاوز الإعدادات الذكية", timelineGesture: "اسحب للتنقل · Ctrl+العجلة للتكبير",
  decision_target_trim: "تم تطبيق المدة المستهدفة", decision_smart_layout: "تم اكتشاف تخطيط الشاشة + الكاميرا"
});
Object.assign(es, {
  shortPromise: "Historia compacta · 9:16 · encuadre automático", youtubePromise: "Conserva la estructura · elimina silencios largos",
  shortModeTitle: "CUTROOM construye el Short por ti", shortModeText: "Director elige los momentos más fuertes, conserva el contexto, respeta la duración y detecta pantalla + cámara automáticamente.",
  youtubeModeTitle: "Limpieza de YouTube sin cambiar la historia", youtubeModeText: "Mantiene el orden y encuadre originales. Acorta el silencio medido y nivela la voz sin cortes semánticos por defecto.",
  podcastModeTitle: "Clip de conversación centrado en el hablante", podcastModeText: "Conserva ideas completas, elimina tiempos muertos y usa los ángulos disponibles sin cambiar en exceso.",
  cleanModeTitle: "Limpia la grabación y conserva la estructura", cleanModeText: "Limpieza conservadora de pausas largas y niveles de audio manteniendo la secuencia original.",
  editCharacter: "Carácter del montaje", editCharacterHelp: "Solo cámbialo si quieres anular los ajustes inteligentes", timelineGesture: "Arrastrar = scrub · Ctrl+rueda = zoom",
  decision_target_trim: "Duración objetivo aplicada", decision_smart_layout: "Diseño pantalla + cámara detectado"
});
Object.assign(fr, {
  shortPromise: "Histoire resserrée · 9:16 · cadrage automatique", youtubePromise: "Préserve la structure · retire les longs silences",
  shortModeTitle: "CUTROOM construit le Short pour vous", shortModeText: "Director choisit les meilleurs moments, garde le contexte, respecte la durée et détecte automatiquement écran + caméra.",
  youtubeModeTitle: "Nettoyage YouTube sans changer l'histoire", youtubeModeText: "Conserve l'ordre et le cadrage d'origine. Raccourcit les silences mesurés et équilibre la voix sans coupe sémantique par défaut.",
  podcastModeTitle: "Extrait de conversation centré sur l'orateur", podcastModeText: "Conserve les idées complètes, retire les temps morts et utilise les angles disponibles sans trop de changements.",
  cleanModeTitle: "Nettoyer l'enregistrement tout en gardant sa structure", cleanModeText: "Nettoyage conservateur des longues pauses et niveaux audio en gardant la séquence d'origine.",
  editCharacter: "Caractère du montage", editCharacterHelp: "À modifier uniquement pour remplacer les réglages intelligents", timelineGesture: "Glisser = scrub · Ctrl+molette = zoom",
  decision_target_trim: "Durée cible appliquée", decision_smart_layout: "Disposition écran + caméra détectée"
});
Object.assign(ru, {
  shortPromise: "Плотная история · 9:16 · автокадрирование", youtubePromise: "Сохраняет структуру · убирает длинные паузы",
  shortModeTitle: "CUTROOM собирает Short за вас", shortModeText: "Director выбирает сильные моменты, сохраняет контекст, соблюдает заданную длину и автоматически определяет экран + камеру.",
  youtubeModeTitle: "Очистка YouTube без изменения истории", youtubeModeText: "Сохраняет исходный порядок и кадрирование. Сокращает измеренные паузы и выравнивает речь без смысловых вырезок по умолчанию.",
  podcastModeTitle: "Фрагмент разговора с фокусом на спикере", podcastModeText: "Сохраняет законченные мысли, убирает простои и использует доступные ракурсы без лишних переключений.",
  cleanModeTitle: "Очистить запись, сохранив структуру", cleanModeText: "Консервативная очистка длинных пауз и уровней звука при сохранении исходной последовательности.",
  editCharacter: "Характер монтажа", editCharacterHelp: "Меняйте только если хотите переопределить умные настройки", timelineGesture: "Перетаскивание = scrub · Ctrl+колесо = zoom",
  decision_target_trim: "Целевая длительность соблюдена", decision_smart_layout: "Обнаружен экран + камера"
});


Object.assign(en, {
  audioCutSetup: "Audio cut line", audioCutTitle: "Choose what counts as silence before Director starts", audioCutHelp: "This is the real level map from your selected audio source. Audio below the yellow line is only a silence candidate when it stays there long enough.",
  recommended: "Recommended", useRecommended: "Use recommended", activeAudio: "Speech / active audio", belowThreshold: "Below threshold — cut candidate", thresholdLine: "Cut line", silenceBelow: "Silence below", silenceBelowHelp: "Move the line until only regions you genuinely want shortened remain below it.", estimatedAudioCut: "With your settings", audioEstimate: "{ranges} quiet regions · ~{seconds}s removed", measuringAudio: "Measuring audio…", audioAvailableSoon: "The dB map appears before proxy preparation finishes.",
  audioGraphClick: "Click the graph to audition that moment. Detected speech is protected from automatic silence cuts.",
  burnCaptions: "Burn captions into video", burnCaptionsHelp: "CUTROOM retimes the transcript after cuts and renders it directly into the MP4.", sourceTime: "Source time", decision_story_selection: "Story passages selected from the full recording"
});
Object.assign(he, {
  audioCutSetup: "קו חיתוך אודיו", audioCutTitle: "קבע מה נחשב שקט לפני שה־Director מתחיל", audioCutHelp: "זהו גרף העוצמה האמיתי של מקור הקול שבחרת. סאונד שמתחת לקו הצהוב הוא רק מועמד לשקט — ורק אם הוא נשאר שם מספיק זמן.",
  recommended: "מומלץ", useRecommended: "השתמש במומלץ", activeAudio: "דיבור / סאונד פעיל", belowThreshold: "מתחת לסף — מועמד לחיתוך", thresholdLine: "קו החיתוך", silenceBelow: "שקט מתחת ל־", silenceBelowHelp: "הזז את הקו עד שרק האזורים שאתה באמת רוצה לקצר נשארים מתחתיו.", estimatedAudioCut: "לפי הבחירה שלך", audioEstimate: "{ranges} אזורי שקט · כ־{seconds} שניות יתקצרו", measuringAudio: "מודד את הסאונד…", audioAvailableSoon: "גרף ה־dB יופיע עוד לפני שה־Proxy יסיים להתכונן.",
  audioGraphClick: "לחץ על הגרף כדי לשמוע את האזור. דיבור מזוהה מוגן מחיתוך אוטומטי.",
  burnCaptions: "צרוב כתוביות בסרטון", burnCaptionsHelp: "CUTROOM מתזמנת את התמלול מחדש אחרי החיתוכים וצורבת אותו ישירות לתוך ה־MP4.", sourceTime: "זמן במקור", decision_story_selection: "נבחרו קטעי סיפור מכל אורך הסרטון"
});
Object.assign(ar, {
  audioCutSetup: "خط قص الصوت", audioCutTitle: "حدد ما يُعتبر صمتاً قبل بدء Director", audioCutHelp: "هذه خريطة المستوى الحقيقية لمصدر الصوت المحدد. الصوت تحت الخط الأصفر يصبح مرشحاً للصمت فقط إذا استمر مدة كافية.",
  recommended: "موصى به", useRecommended: "استخدم الموصى به", activeAudio: "كلام / صوت نشط", belowThreshold: "تحت الحد — مرشح للقص", thresholdLine: "خط القص", silenceBelow: "الصمت تحت", silenceBelowHelp: "حرّك الخط حتى تبقى تحته فقط المناطق التي تريد تقصيرها فعلاً.", estimatedAudioCut: "وفق إعداداتك", audioEstimate: "{ranges} مناطق صمت · إزالة نحو {seconds}ث", measuringAudio: "جارٍ قياس الصوت…", audioAvailableSoon: "ستظهر خريطة dB قبل اكتمال إعداد الـProxy.",
  audioGraphClick: "انقر على الرسم لسماع تلك اللحظة. الكلام المكتشف محمي من قص الصمت التلقائي.",
  burnCaptions: "حرق الترجمة داخل الفيديو", burnCaptionsHelp: "يعيد CUTROOM توقيت النص بعد القص ويطبعه مباشرة داخل MP4.", sourceTime: "وقت المصدر", decision_story_selection: "تم اختيار مقاطع القصة من كامل التسجيل"
});
Object.assign(es, {
  audioCutSetup: "Línea de corte de audio", audioCutTitle: "Decide qué cuenta como silencio antes de iniciar Director", audioCutHelp: "Este es el mapa de nivel real de la fuente de audio elegida. El audio bajo la línea amarilla solo es candidato a silencio si permanece allí el tiempo suficiente.",
  recommended: "Recomendado", useRecommended: "Usar recomendado", activeAudio: "Voz / audio activo", belowThreshold: "Bajo el umbral — candidato a corte", thresholdLine: "Línea de corte", silenceBelow: "Silencio por debajo de", silenceBelowHelp: "Mueve la línea hasta que solo queden debajo las zonas que realmente quieres acortar.", estimatedAudioCut: "Con tus ajustes", audioEstimate: "{ranges} zonas silenciosas · ~{seconds}s eliminados", measuringAudio: "Midiendo audio…", audioAvailableSoon: "El mapa dB aparece antes de que termine el proxy.",
  audioGraphClick: "Haz clic en el gráfico para escuchar ese momento. La voz detectada se protege de los cortes automáticos de silencio.",
  burnCaptions: "Incrustar subtítulos en el vídeo", burnCaptionsHelp: "CUTROOM reajusta los tiempos tras los cortes y renderiza el texto dentro del MP4.", sourceTime: "Tiempo de origen", decision_story_selection: "Fragmentos de historia seleccionados de toda la grabación"
});
Object.assign(fr, {
  audioCutSetup: "Seuil de coupe audio", audioCutTitle: "Définissez ce qui compte comme silence avant Director", audioCutHelp: "Voici la carte de niveau réelle de la source audio choisie. L'audio sous la ligne jaune n'est candidat au silence que s'il y reste assez longtemps.",
  recommended: "Recommandé", useRecommended: "Utiliser recommandé", activeAudio: "Voix / audio actif", belowThreshold: "Sous le seuil — candidat à la coupe", thresholdLine: "Ligne de coupe", silenceBelow: "Silence sous", silenceBelowHelp: "Déplacez la ligne jusqu'à ce que seules les zones à raccourcir restent dessous.", estimatedAudioCut: "Avec vos réglages", audioEstimate: "{ranges} zones calmes · ~{seconds}s retirées", measuringAudio: "Mesure de l'audio…", audioAvailableSoon: "La carte dB apparaît avant la fin du proxy.",
  audioGraphClick: "Cliquez sur le graphe pour écouter ce moment. La parole détectée est protégée des coupes automatiques de silence.",
  burnCaptions: "Incruster les sous-titres", burnCaptionsHelp: "CUTROOM recale le transcript après les coupes et le rend directement dans le MP4.", sourceTime: "Temps source", decision_story_selection: "Passages narratifs choisis dans tout l'enregistrement"
});
Object.assign(ru, {
  audioCutSetup: "Линия среза аудио", audioCutTitle: "Укажите, что считать тишиной до запуска Director", audioCutHelp: "Это реальная карта уровня выбранного источника звука. Звук ниже жёлтой линии считается кандидатом на тишину только если держится там достаточно долго.",
  recommended: "Рекомендуется", useRecommended: "Использовать", activeAudio: "Речь / активный звук", belowThreshold: "Ниже порога — кандидат на вырезание", thresholdLine: "Линия среза", silenceBelow: "Тишина ниже", silenceBelowHelp: "Перемещайте линию, пока ниже не останутся только участки, которые действительно хотите сократить.", estimatedAudioCut: "По вашим настройкам", audioEstimate: "{ranges} тихих участков · ~{seconds}с будет убрано", measuringAudio: "Измерение аудио…", audioAvailableSoon: "Карта dB появится до окончания подготовки proxy.",
  audioGraphClick: "Нажмите на график, чтобы прослушать этот момент. Обнаруженная речь защищена от автоматического удаления тишины.",
  burnCaptions: "Вжечь субтитры в видео", burnCaptionsHelp: "CUTROOM пересчитывает тайминг после склеек и рендерит текст прямо в MP4.", sourceTime: "Время источника", decision_story_selection: "Сюжетные фрагменты выбраны по всей записи"
});

Object.assign(en, {
  taskListen: "Transcription and chapters", taskStory: "Whole-video story outline", taskSync: "Selecting moments and framing", taskDraft: "Continuity check and final draft",
  ollamaRequired: "Story AI requires Ollama to be running. Start Ollama and try again.", storyModelRequired: "The Story AI model is required for Shorts and podcasts.",
  aiPartial: "Story AI is required for semantic Shorts. YouTube dead-air cleanup can work without it."
});
Object.assign(he, {
  taskListen: "תמלול וחלוקה לפרקים", taskStory: "הבנת הסיפור של כל הסרטון", taskSync: "בחירת הרגעים והמסגור", taskDraft: "בדיקת רצף ובניית העריכה",
  ollamaRequired: "Story AI דורש ש־Ollama יהיה פעיל. הפעל את Ollama ונסה שוב.", storyModelRequired: "מודל Story AI נדרש ל־Shorts ולפודקאסטים.",
  aiPartial: "Story AI נדרש לעריכת Short סמנטית. ניקוי Dead Air של YouTube יכול לעבוד בלעדיו."
});
Object.assign(ar, {
  taskListen: "التفريغ وتقسيم الفصول", taskStory: "فهم قصة الفيديو بالكامل", taskSync: "اختيار اللحظات والتأطير", taskDraft: "فحص الاستمرارية وبناء المونتاج",
  ollamaRequired: "يتطلب Story AI تشغيل Ollama.", storyModelRequired: "نموذج Story AI مطلوب للمقاطع القصيرة والبودكاست.",
  aiPartial: "Story AI مطلوب للمونتاج الدلالي؛ تنظيف YouTube من الصمت يعمل بدونه."
});
Object.assign(es, {
  taskListen: "Transcripción y capítulos", taskStory: "Comprender la historia completa", taskSync: "Elegir momentos y encuadre", taskDraft: "Revisar continuidad y montar",
  ollamaRequired: "Story AI necesita que Ollama esté en ejecución.", storyModelRequired: "El modelo Story AI es necesario para Shorts y podcasts.",
  aiPartial: "Story AI es necesario para Shorts semánticos; la limpieza de YouTube funciona sin él."
});
Object.assign(fr, {
  taskListen: "Transcription et chapitres", taskStory: "Compréhension de toute l’histoire", taskSync: "Sélection des moments et cadrage", taskDraft: "Vérification de continuité et montage",
  ollamaRequired: "Story AI nécessite qu’Ollama soit lancé.", storyModelRequired: "Le modèle Story AI est requis pour Shorts et podcasts.",
  aiPartial: "Story AI est requis pour les Shorts sémantiques; le nettoyage YouTube fonctionne sans lui."
});
Object.assign(ru, {
  taskListen: "Транскрипция и главы", taskStory: "Понимание истории целиком", taskSync: "Выбор моментов и кадрирование", taskDraft: "Проверка связности и монтаж",
  ollamaRequired: "Для Story AI должен быть запущен Ollama.", storyModelRequired: "Модель Story AI нужна для Shorts и подкастов.",
  aiPartial: "Story AI нужен для смысловых Shorts; очистка YouTube от пауз работает без него."
});

Object.assign(en, {
  stopProcess: "Stop process", cancelling: "Stopping safely…", cancelAccepted: "Stop requested. CUTROOM will finish the current safe checkpoint.", cancelQueued: "Stop requested. Pending work will be cancelled before it starts.", cancelFailed: "Could not stop the process",
  rebuildBeforeRefine: "Rebuild the Draft to apply your changed settings before refining, loading another edit or exporting.",
  anotherCutUnchanged: "No different cut found with the current settings. Your edit was kept.",
  limitedHighlightWarning: "The result is shorter than requested because the recording did not contain enough distinct strong moments.",
  audioHighlightWarning: "This draft uses audio activity and scene changes because speech could not be transcribed reliably. Spoken context may be missing. If your footage contains speech, check its language and audio source, then rebuild.",
  storyFallbackWarning: "Story AI was unavailable for this draft. A fallback edit was built from the transcript; review the selected moments before exporting.",
  reviewSpeechSettings: "Review speech settings",
  decision_audio_highlights: "Audio + visual highlights selected from the recording",
  activeUpload: "Importing footage", uploadCancelled: "Footage import stopped",
  activeDirector: "Director is working", activeExport: "Export is running", activeModel: "AI setup is running",
  editorialEffects: "Smart editorial effects", editorialEffectsHelp: "Subtle, bounded emphasis at story peaks; no extra model and no free-form AI commands.",
  shortModeText: "Director chooses the strongest moments, preserves context and frames automatically. Screen + camera is used only after you confirm it.",
  editStyleEvidence: "Each style changes moment selection, pacing and duration. Screen + camera is never enabled without explicit confirmation.",
  decision_smart_layout: "Screen + camera layout confirmed",
  notEnoughRenderDisk: "Not enough free disk space to render safely. CUTROOM needs about {required}; {free} is free."
});
Object.assign(he, {
  stopProcess: "עצור תהליך", cancelling: "עוצר בבטחה…", cancelAccepted: "בקשת העצירה התקבלה. CUTROOM תסיים את נקודת הבטיחות הנוכחית.", cancelQueued: "התהליך ייעצר מיד כשהעבודה תיווצר.", cancelFailed: "לא הצלחנו לעצור את התהליך",
  activeUpload: "מייבא חומר גלם", uploadCancelled: "ייבוא חומר הגלם נעצר",
  activeDirector: "ה־Director עובד", activeExport: "הייצוא מתבצע", activeModel: "מנוע ה־AI בהכנה",
  editorialEffects: "אפקטים עריכתיים חכמים", editorialEffectsHelp: "הדגשות צבע עדינות ומוגבלות בנקודות שיא; ללא מודל נוסף וללא פקודות AI חופשיות.",
  shortModeText: "ה־Director בוחר את הרגעים החזקים, שומר Context וממסגר אוטומטית. פריסת מסך + מצלמה מופעלת רק אחרי אישור.",
  editStyleEvidence: "כל סגנון משנה את בחירת הרגעים, הקצב והאורך. פריסת מסך + מצלמה לעולם לא מופעלת בלי אישור מפורש.",
  decision_smart_layout: "פריסת מסך + מצלמה אושרה",
  notEnoughRenderDisk: "אין מספיק מקום פנוי לייצוא בטוח. CUTROOM צריכה בערך {required}, וכרגע פנויים {free}."
});
Object.assign(ar, {
  editorialEffects: "مؤثرات تحرير ذكية", editorialEffectsHelp: "تأكيدات لونية خفيفة ومحدودة عند ذروة القصة؛ بلا نموذج إضافي أو أوامر AI حرة.",
  shortModeText: "يختار Director أقوى اللحظات ويحافظ على السياق ويؤطر تلقائياً. لا يُستخدم تخطيط الشاشة + الكاميرا إلا بعد تأكيدك.",
  decision_smart_layout: "تم تأكيد تخطيط الشاشة + الكاميرا"
});
Object.assign(es, {
  editorialEffects: "Efectos editoriales inteligentes", editorialEffectsHelp: "Énfasis sutil y limitado en los picos de la historia; sin otro modelo ni comandos de IA libres.",
  shortModeText: "Director elige los momentos más fuertes, conserva el contexto y encuadra automáticamente. Pantalla + cámara solo se usa después de tu confirmación.",
  decision_smart_layout: "Diseño pantalla + cámara confirmado"
});
Object.assign(fr, {
  editorialEffects: "Effets éditoriaux intelligents", editorialEffectsHelp: "Accentuation subtile et limitée aux temps forts; sans modèle supplémentaire ni commandes IA libres.",
  shortModeText: "Director choisit les meilleurs moments, garde le contexte et cadre automatiquement. La disposition écran + caméra n’est utilisée qu’après votre confirmation.",
  decision_smart_layout: "Disposition écran + caméra confirmée"
});
Object.assign(ru, {
  editorialEffects: "Умные монтажные эффекты", editorialEffectsHelp: "Мягкие ограниченные акценты в кульминациях; без дополнительной модели и свободных AI-команд.",
  shortModeText: "Director выбирает сильные моменты, сохраняет контекст и автоматически кадрирует. Компоновка экран + камера используется только после подтверждения.",
  decision_smart_layout: "Компоновка экран + камера подтверждена"
});

export const dictionaries = { en, he, ar, es, fr, ru };
export const RTL_LANGUAGES = new Set(["he", "ar"]);

export function detectLanguageFromText(text, fallback = "en") {
  const value = String(text || "");
  const counts = {
    he: (value.match(/[\u0590-\u05FF]/g) || []).length,
    ar: (value.match(/[\u0600-\u06FF]/g) || []).length,
    ru: (value.match(/[\u0400-\u04FF]/g) || []).length,
    latin: (value.match(/[A-Za-zÀ-ÿ]/g) || []).length,
  };
  const total = Object.values(counts).reduce((sum, amount) => sum + amount, 0);
  const [script, amount] = Object.entries(counts).sort((a,b) => b[1] - a[1])[0];
  if (total < 4 || amount / Math.max(1,total) < 0.64) return fallback;
  if (["he", "ar", "ru"].includes(script) && amount >= 4) return script;
  if (script !== "latin" || amount < 12) return fallback;
  const normalized = ` ${value.toLowerCase()} `;
  const spanish = (normalized.match(/\b(el|la|que|para|una|gracias|quiero|vídeo|como|con|por)\b/g) || []).length;
  const french = (normalized.match(/\b(le|les|une|pour|avec|merci|vidéo|je|des|est|dans)\b/g) || []).length;
  if (spanish >= 2 && spanish > french) return "es";
  if (french >= 2 && french > spanish) return "fr";
  return "en";
}

export function resolveInitialLanguage() {
  return "en";
}

export function applyTranslations() {
  const dictionary = en;
  document.documentElement.lang = "en";
  document.documentElement.dir = "ltr";
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    const key = element.dataset.i18n;
    const value = dictionary[key] ?? en[key];
    if (value != null) element.textContent = value;
  });
  document.querySelectorAll('input[type="text"], input[type="search"], textarea').forEach((element) => { element.dir = "auto"; });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    const key = element.dataset.i18nPlaceholder;
    const value = dictionary[key] ?? en[key];
    if (value != null) element.setAttribute("placeholder", value);
  });
  return dictionary;
}
