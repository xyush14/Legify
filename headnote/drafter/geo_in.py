"""District / city → State, in both scripts — so a brief that says "Gwalior" or
"ग्वालियर" can fill the State on a filing without anyone typing it.

Why this exists: every reviewed court template prints the State twice — after the
court name, "(मध्यप्रदेश)", and as the respondent, "मध्यप्रदेश शासन द्वारा". With no
way to derive it, every draft carried "________ शासन" and "(________)" even when the
advocate had named the district. Guessing a State would be worse than a blank, so
this table is deliberately conservative:

  • Names that exist in MORE THAN ONE State (Aurangabad, Bilaspur, Hamirpur,
    Pratapgarh, Balrampur, Bijapur, Raigarh …) resolve to NO State. The caller
    then leaves the blank, rather than filing a Bihar matter against the
    Maharashtra government.
  • A place that is not in the table resolves to nothing. Nothing defaults to MP.

Coverage is complete for the Hindi-belt States where most district advocates
practise (MP, UP, Bihar, Rajasthan, Chhattisgarh, Jharkhand, Haryana,
Uttarakhand, Himachal, Delhi, Punjab) and covers the district headquarters and
major court towns of every other large State. Adding a place is one row.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# state key → (Hindi, English) — the words a filing uses for the State
STATES: dict[str, tuple[str, str]] = {
    "mp": ("मध्यप्रदेश", "Madhya Pradesh"),
    "up": ("उत्तर प्रदेश", "Uttar Pradesh"),
    "bihar": ("बिहार", "Bihar"),
    "rajasthan": ("राजस्थान", "Rajasthan"),
    "cg": ("छत्तीसगढ़", "Chhattisgarh"),
    "jharkhand": ("झारखण्ड", "Jharkhand"),
    "haryana": ("हरियाणा", "Haryana"),
    "uttarakhand": ("उत्तराखण्ड", "Uttarakhand"),
    "hp": ("हिमाचल प्रदेश", "Himachal Pradesh"),
    "delhi": ("दिल्ली", "Delhi"),
    "punjab": ("पंजाब", "Punjab"),
    "chandigarh": ("चण्डीगढ़", "Chandigarh"),
    "maharashtra": ("महाराष्ट्र", "Maharashtra"),
    "gujarat": ("गुजरात", "Gujarat"),
    "karnataka": ("कर्नाटक", "Karnataka"),
    "tn": ("तमिलनाडु", "Tamil Nadu"),
    "telangana": ("तेलंगाना", "Telangana"),
    "ap": ("आन्ध्र प्रदेश", "Andhra Pradesh"),
    "wb": ("पश्चिम बंगाल", "West Bengal"),
    "odisha": ("ओडिशा", "Odisha"),
    "kerala": ("केरल", "Kerala"),
    "assam": ("असम", "Assam"),
    "jk": ("जम्मू-कश्मीर", "Jammu & Kashmir"),
    "goa": ("गोवा", "Goa"),
}

# How a brief names a State directly. Two-letter abbreviations are matched only in
# the ORIGINAL casing ("MP", "U.P.") — lowercase "up"/"mp" are ordinary words.
_STATE_ALIASES: dict[str, str] = {
    "madhya pradesh": "mp", "मध्यप्रदेश": "mp", "मध्य प्रदेश": "mp", "म.प्र.": "mp", "म. प्र.": "mp",
    "uttar pradesh": "up", "उत्तर प्रदेश": "up", "उत्तरप्रदेश": "up", "उ.प्र.": "up", "उ. प्र.": "up",
    "bihar": "bihar", "बिहार": "bihar",
    "rajasthan": "rajasthan", "राजस्थान": "rajasthan",
    "chhattisgarh": "cg", "chattisgarh": "cg", "छत्तीसगढ़": "cg", "छ.ग.": "cg",
    "jharkhand": "jharkhand", "झारखण्ड": "jharkhand", "झारखंड": "jharkhand",
    "haryana": "haryana", "हरियाणा": "haryana",
    "uttarakhand": "uttarakhand", "उत्तराखण्ड": "uttarakhand", "उत्तराखंड": "uttarakhand",
    "himachal pradesh": "hp", "हिमाचल प्रदेश": "hp", "हि.प्र.": "hp",
    "delhi": "delhi", "new delhi": "delhi", "दिल्ली": "delhi", "नई दिल्ली": "delhi",
    "punjab": "punjab", "पंजाब": "punjab",
    "chandigarh": "chandigarh", "चण्डीगढ़": "chandigarh", "चंडीगढ़": "chandigarh",
    "maharashtra": "maharashtra", "महाराष्ट्र": "maharashtra",
    "gujarat": "gujarat", "गुजरात": "gujarat",
    "karnataka": "karnataka", "कर्नाटक": "karnataka",
    "tamil nadu": "tn", "तमिलनाडु": "tn",
    "telangana": "telangana", "तेलंगाना": "telangana",
    "andhra pradesh": "ap", "आन्ध्र प्रदेश": "ap", "आंध्र प्रदेश": "ap",
    "west bengal": "wb", "पश्चिम बंगाल": "wb",
    "odisha": "odisha", "orissa": "odisha", "ओडिशा": "odisha", "उड़ीसा": "odisha",
    "kerala": "kerala", "केरल": "kerala",
    "assam": "assam", "असम": "assam",
    "jammu and kashmir": "jk", "jammu & kashmir": "jk", "जम्मू-कश्मीर": "jk", "जम्मू कश्मीर": "jk",
    "goa": "goa", "गोवा": "goa",
}
_STATE_ABBR_CASED = {"MP": "mp", "M.P.": "mp", "UP": "up", "U.P.": "up", "CG": "cg", "C.G.": "cg",
                     "HP": "hp", "H.P.": "hp", "J&K": "jk", "WB": "wb", "TN": "tn"}

# (English aliases separated by "|", Hindi, state). The first English alias is the
# display name; the Hindi is what a Hindi filing prints.
_ROWS: list[tuple[str, str, str]] = [
    # ---------------------------------------------------------------- Madhya Pradesh
    ("Agar Malwa|Agar", "आगर मालवा", "mp"), ("Alirajpur", "अलीराजपुर", "mp"),
    ("Anuppur", "अनूपपुर", "mp"), ("Ashoknagar|Ashok Nagar", "अशोकनगर", "mp"),
    ("Balaghat", "बालाघाट", "mp"), ("Barwani", "बड़वानी", "mp"), ("Betul", "बैतूल", "mp"),
    ("Bhind", "भिण्ड", "mp"), ("Bhopal", "भोपाल", "mp"), ("Burhanpur", "बुरहानपुर", "mp"),
    ("Chhatarpur", "छतरपुर", "mp"), ("Chhindwara", "छिंदवाड़ा", "mp"), ("Damoh", "दमोह", "mp"),
    ("Datia", "दतिया", "mp"), ("Dewas", "देवास", "mp"), ("Dhar", "धार", "mp"),
    ("Dindori", "डिंडोरी", "mp"), ("Guna", "गुना", "mp"), ("Gwalior", "ग्वालियर", "mp"),
    ("Harda", "हरदा", "mp"), ("Narmadapuram|Hoshangabad", "नर्मदापुरम", "mp"),
    ("Indore", "इंदौर", "mp"), ("Jabalpur", "जबलपुर", "mp"), ("Jhabua", "झाबुआ", "mp"),
    ("Katni", "कटनी", "mp"), ("Khandwa", "खंडवा", "mp"), ("Khargone", "खरगोन", "mp"),
    ("Mandla", "मंडला", "mp"), ("Mandsaur", "मंदसौर", "mp"), ("Morena", "मुरैना", "mp"),
    ("Narsinghpur", "नरसिंहपुर", "mp"), ("Neemuch", "नीमच", "mp"), ("Niwari", "निवाड़ी", "mp"),
    ("Panna", "पन्ना", "mp"), ("Raisen", "रायसेन", "mp"), ("Rajgarh", "राजगढ़", "mp"),
    ("Ratlam", "रतलाम", "mp"), ("Rewa", "रीवा", "mp"), ("Sagar", "सागर", "mp"),
    ("Satna", "सतना", "mp"), ("Sehore", "सीहोर", "mp"), ("Seoni", "सिवनी", "mp"),
    ("Shahdol", "शहडोल", "mp"), ("Shajapur", "शाजापुर", "mp"), ("Sheopur", "श्योपुर", "mp"),
    ("Shivpuri", "शिवपुरी", "mp"), ("Sidhi", "सीधी", "mp"), ("Singrauli", "सिंगरौली", "mp"),
    ("Tikamgarh", "टीकमगढ़", "mp"), ("Ujjain", "उज्जैन", "mp"), ("Umaria", "उमरिया", "mp"),
    ("Vidisha", "विदिशा", "mp"), ("Mauganj", "मऊगंज", "mp"), ("Maihar", "मैहर", "mp"),
    ("Pandhurna", "पांढुर्णा", "mp"),
    # ---------------------------------------------------------------- Uttar Pradesh
    ("Agra", "आगरा", "up"), ("Aligarh", "अलीगढ़", "up"), ("Ambedkar Nagar", "अम्बेडकर नगर", "up"),
    ("Amethi", "अमेठी", "up"), ("Amroha", "अमरोहा", "up"), ("Auraiya", "औरैया", "up"),
    ("Ayodhya|Faizabad", "अयोध्या", "up"), ("Azamgarh", "आजमगढ़", "up"), ("Baghpat", "बागपत", "up"),
    ("Bahraich", "बहराइच", "up"), ("Ballia", "बलिया", "up"), ("Banda", "बांदा", "up"),
    ("Barabanki", "बाराबंकी", "up"), ("Bareilly", "बरेली", "up"), ("Basti", "बस्ती", "up"),
    ("Bhadohi|Sant Ravidas Nagar", "भदोही", "up"), ("Bijnor", "बिजनौर", "up"),
    ("Budaun|Badaun", "बदायूं", "up"), ("Bulandshahr", "बुलंदशहर", "up"),
    ("Chandauli", "चंदौली", "up"), ("Chitrakoot", "चित्रकूट", "up"), ("Deoria", "देवरिया", "up"),
    ("Etah", "एटा", "up"), ("Etawah", "इटावा", "up"), ("Farrukhabad", "फर्रुखाबाद", "up"),
    ("Fatehpur", "फतेहपुर", "up"), ("Firozabad", "फिरोजाबाद", "up"),
    ("Gautam Buddh Nagar|Noida|Greater Noida", "गौतम बुद्ध नगर", "up"),
    ("Ghaziabad", "गाजियाबाद", "up"), ("Ghazipur", "गाजीपुर", "up"), ("Gonda", "गोंडा", "up"),
    ("Gorakhpur", "गोरखपुर", "up"), ("Hapur", "हापुड़", "up"), ("Hardoi", "हरदोई", "up"),
    ("Hathras", "हाथरस", "up"), ("Jalaun|Orai", "जालौन", "up"), ("Jaunpur", "जौनपुर", "up"),
    ("Jhansi", "झांसी", "up"), ("Kannauj", "कन्नौज", "up"), ("Kanpur Dehat", "कानपुर देहात", "up"),
    ("Kanpur Nagar|Kanpur", "कानपुर नगर", "up"), ("Kasganj", "कासगंज", "up"),
    ("Kaushambi", "कौशाम्बी", "up"), ("Kushinagar", "कुशीनगर", "up"),
    ("Lakhimpur Kheri|Lakhimpur", "लखीमपुर खीरी", "up"), ("Lalitpur", "ललितपुर", "up"),
    ("Lucknow", "लखनऊ", "up"), ("Maharajganj", "महराजगंज", "up"), ("Mahoba", "महोबा", "up"),
    ("Mainpuri", "मैनपुरी", "up"), ("Mathura", "मथुरा", "up"), ("Mau", "मऊ", "up"),
    ("Meerut", "मेरठ", "up"), ("Mirzapur", "मिर्जापुर", "up"), ("Moradabad", "मुरादाबाद", "up"),
    ("Muzaffarnagar", "मुजफ्फरनगर", "up"), ("Pilibhit", "पीलीभीत", "up"),
    ("Prayagraj|Allahabad", "प्रयागराज", "up"), ("Raebareli|Rae Bareli", "रायबरेली", "up"),
    ("Rampur", "रामपुर", "up"), ("Saharanpur", "सहारनपुर", "up"), ("Sambhal", "सम्भल", "up"),
    ("Sant Kabir Nagar", "संत कबीर नगर", "up"), ("Shahjahanpur", "शाहजहांपुर", "up"),
    ("Shamli", "शामली", "up"), ("Shravasti", "श्रावस्ती", "up"),
    ("Siddharthnagar", "सिद्धार्थनगर", "up"), ("Sitapur", "सीतापुर", "up"),
    ("Sonbhadra", "सोनभद्र", "up"), ("Sultanpur", "सुल्तानपुर", "up"), ("Unnao", "उन्नाव", "up"),
    ("Varanasi|Banaras|Benares", "वाराणसी", "up"),
    # ---------------------------------------------------------------- Bihar
    ("Araria", "अररिया", "bihar"), ("Arwal", "अरवल", "bihar"), ("Banka", "बांका", "bihar"),
    ("Begusarai", "बेगूसराय", "bihar"), ("Bhagalpur", "भागलपुर", "bihar"),
    ("Bhojpur|Ara|Arrah", "भोजपुर", "bihar"), ("Buxar", "बक्सर", "bihar"),
    ("Darbhanga", "दरभंगा", "bihar"), ("East Champaran|Motihari", "पूर्वी चम्पारण", "bihar"),
    ("Gaya", "गया", "bihar"), ("Gopalganj", "गोपालगंज", "bihar"), ("Jamui", "जमुई", "bihar"),
    ("Jehanabad", "जहानाबाद", "bihar"), ("Kaimur|Bhabua", "कैमूर", "bihar"),
    ("Katihar", "कटिहार", "bihar"), ("Khagaria", "खगड़िया", "bihar"),
    ("Kishanganj", "किशनगंज", "bihar"), ("Lakhisarai", "लखीसराय", "bihar"),
    ("Madhepura", "मधेपुरा", "bihar"), ("Madhubani", "मधुबनी", "bihar"), ("Munger", "मुंगेर", "bihar"),
    ("Muzaffarpur", "मुजफ्फरपुर", "bihar"), ("Nalanda|Bihar Sharif", "नालंदा", "bihar"),
    ("Nawada", "नवादा", "bihar"), ("Patna", "पटना", "bihar"), ("Purnia", "पूर्णिया", "bihar"),
    ("Rohtas|Sasaram", "रोहतास", "bihar"), ("Saharsa", "सहरसा", "bihar"),
    ("Samastipur", "समस्तीपुर", "bihar"), ("Saran|Chhapra", "सारण", "bihar"),
    ("Sheikhpura", "शेखपुरा", "bihar"), ("Sheohar", "शिवहर", "bihar"),
    ("Sitamarhi", "सीतामढ़ी", "bihar"), ("Siwan", "सिवान", "bihar"), ("Supaul", "सुपौल", "bihar"),
    ("Vaishali|Hajipur", "वैशाली", "bihar"), ("West Champaran|Bettiah", "पश्चिमी चम्पारण", "bihar"),
    # ---------------------------------------------------------------- Rajasthan
    ("Ajmer", "अजमेर", "rajasthan"), ("Alwar", "अलवर", "rajasthan"),
    ("Banswara", "बांसवाड़ा", "rajasthan"), ("Baran", "बारां", "rajasthan"),
    ("Barmer", "बाड़मेर", "rajasthan"), ("Bharatpur", "भरतपुर", "rajasthan"),
    ("Bhilwara", "भीलवाड़ा", "rajasthan"), ("Bikaner", "बीकानेर", "rajasthan"),
    ("Bundi", "बूंदी", "rajasthan"), ("Chittorgarh|Chittor", "चित्तौड़गढ़", "rajasthan"),
    ("Churu", "चूरू", "rajasthan"), ("Dausa", "दौसा", "rajasthan"), ("Dholpur", "धौलपुर", "rajasthan"),
    ("Dungarpur", "डूंगरपुर", "rajasthan"), ("Hanumangarh", "हनुमानगढ़", "rajasthan"),
    ("Jaipur", "जयपुर", "rajasthan"), ("Jaisalmer", "जैसलमेर", "rajasthan"),
    ("Jalore", "जालोर", "rajasthan"), ("Jhalawar", "झालावाड़", "rajasthan"),
    ("Jhunjhunu", "झुंझुनूं", "rajasthan"), ("Jodhpur", "जोधपुर", "rajasthan"),
    ("Karauli", "करौली", "rajasthan"), ("Kota", "कोटा", "rajasthan"), ("Nagaur", "नागौर", "rajasthan"),
    ("Pali", "पाली", "rajasthan"), ("Rajsamand", "राजसमंद", "rajasthan"),
    ("Sawai Madhopur", "सवाई माधोपुर", "rajasthan"), ("Sikar", "सीकर", "rajasthan"),
    ("Sirohi", "सिरोही", "rajasthan"), ("Sri Ganganagar|Ganganagar", "श्रीगंगानगर", "rajasthan"),
    ("Tonk", "टोंक", "rajasthan"), ("Udaipur", "उदयपुर", "rajasthan"),
    ("Balotra", "बालोतरा", "rajasthan"), ("Beawar", "ब्यावर", "rajasthan"), ("Deeg", "डीग", "rajasthan"),
    ("Didwana", "डीडवाना", "rajasthan"), ("Kotputli|Behror", "कोटपूतली", "rajasthan"),
    ("Phalodi", "फलोदी", "rajasthan"), ("Salumbar", "सलूम्बर", "rajasthan"),
    # ---------------------------------------------------------------- Chhattisgarh
    ("Balod", "बालोद", "cg"), ("Baloda Bazar", "बलौदाबाजार", "cg"), ("Bastar|Jagdalpur", "बस्तर", "cg"),
    ("Bemetara", "बेमेतरा", "cg"), ("Dantewada", "दंतेवाड़ा", "cg"), ("Dhamtari", "धमतरी", "cg"),
    ("Durg|Bhilai", "दुर्ग", "cg"), ("Gariaband", "गरियाबंद", "cg"),
    ("Janjgir|Janjgir-Champa", "जांजगीर-चांपा", "cg"), ("Jashpur", "जशपुर", "cg"),
    ("Kabirdham|Kawardha", "कबीरधाम", "cg"), ("Kanker", "कांकेर", "cg"), ("Kondagaon", "कोंडागांव", "cg"),
    ("Korba", "कोरबा", "cg"), ("Korea|Koriya", "कोरिया", "cg"), ("Mahasamund", "महासमुंद", "cg"),
    ("Mungeli", "मुंगेली", "cg"), ("Narayanpur", "नारायणपुर", "cg"), ("Raipur", "रायपुर", "cg"),
    ("Rajnandgaon", "राजनांदगांव", "cg"), ("Sukma", "सुकमा", "cg"), ("Surajpur", "सूरजपुर", "cg"),
    ("Surguja|Ambikapur", "सरगुजा", "cg"),
    # ---------------------------------------------------------------- Jharkhand
    ("Bokaro", "बोकारो", "jharkhand"), ("Chatra", "चतरा", "jharkhand"), ("Deoghar", "देवघर", "jharkhand"),
    ("Dhanbad", "धनबाद", "jharkhand"), ("Dumka", "दुमका", "jharkhand"),
    ("East Singhbhum|Jamshedpur", "पूर्वी सिंहभूम", "jharkhand"), ("Garhwa", "गढ़वा", "jharkhand"),
    ("Giridih", "गिरिडीह", "jharkhand"), ("Godda", "गोड्डा", "jharkhand"), ("Gumla", "गुमला", "jharkhand"),
    ("Hazaribagh", "हजारीबाग", "jharkhand"), ("Jamtara", "जामताड़ा", "jharkhand"),
    ("Khunti", "खूंटी", "jharkhand"), ("Koderma", "कोडरमा", "jharkhand"),
    ("Latehar", "लातेहार", "jharkhand"), ("Lohardaga", "लोहरदगा", "jharkhand"),
    ("Pakur", "पाकुड़", "jharkhand"), ("Palamu|Daltonganj", "पलामू", "jharkhand"),
    ("Ranchi", "रांची", "jharkhand"), ("Sahebganj", "साहिबगंज", "jharkhand"),
    ("Seraikela|Saraikela", "सरायकेला-खरसावां", "jharkhand"), ("Simdega", "सिमडेगा", "jharkhand"),
    ("West Singhbhum|Chaibasa", "पश्चिमी सिंहभूम", "jharkhand"),
    # ---------------------------------------------------------------- Haryana
    ("Ambala", "अम्बाला", "haryana"), ("Bhiwani", "भिवानी", "haryana"),
    ("Charkhi Dadri", "चरखी दादरी", "haryana"), ("Faridabad", "फरीदाबाद", "haryana"),
    ("Fatehabad", "फतेहाबाद", "haryana"), ("Gurugram|Gurgaon", "गुरुग्राम", "haryana"),
    ("Hisar|Hissar", "हिसार", "haryana"), ("Jhajjar", "झज्जर", "haryana"), ("Jind", "जींद", "haryana"),
    ("Kaithal", "कैथल", "haryana"), ("Karnal", "करनाल", "haryana"),
    ("Kurukshetra", "कुरुक्षेत्र", "haryana"), ("Mahendragarh|Narnaul", "महेन्द्रगढ़", "haryana"),
    ("Nuh|Mewat", "नूंह", "haryana"), ("Palwal", "पलवल", "haryana"), ("Panchkula", "पंचकुला", "haryana"),
    ("Panipat", "पानीपत", "haryana"), ("Rewari", "रेवाड़ी", "haryana"), ("Rohtak", "रोहतक", "haryana"),
    ("Sirsa", "सिरसा", "haryana"), ("Sonipat", "सोनीपत", "haryana"),
    ("Yamunanagar", "यमुनानगर", "haryana"),
    # ---------------------------------------------------------------- Uttarakhand
    ("Almora", "अल्मोड़ा", "uttarakhand"), ("Bageshwar", "बागेश्वर", "uttarakhand"),
    ("Chamoli", "चमोली", "uttarakhand"), ("Champawat", "चम्पावत", "uttarakhand"),
    ("Dehradun", "देहरादून", "uttarakhand"), ("Haridwar", "हरिद्वार", "uttarakhand"),
    ("Nainital|Haldwani", "नैनीताल", "uttarakhand"), ("Pauri Garhwal|Pauri", "पौड़ी गढ़वाल", "uttarakhand"),
    ("Pithoragarh", "पिथौरागढ़", "uttarakhand"), ("Rudraprayag", "रुद्रप्रयाग", "uttarakhand"),
    ("Tehri Garhwal|Tehri", "टिहरी गढ़वाल", "uttarakhand"),
    ("Udham Singh Nagar|Rudrapur", "ऊधम सिंह नगर", "uttarakhand"),
    ("Uttarkashi", "उत्तरकाशी", "uttarakhand"),
    # ---------------------------------------------------------------- Himachal Pradesh
    ("Chamba", "चम्बा", "hp"), ("Kangra|Dharamshala", "कांगड़ा", "hp"), ("Kinnaur", "किन्नौर", "hp"),
    ("Kullu", "कुल्लू", "hp"), ("Mandi", "मण्डी", "hp"), ("Shimla", "शिमला", "hp"),
    ("Sirmaur|Nahan", "सिरमौर", "hp"), ("Solan", "सोलन", "hp"), ("Una", "ऊना", "hp"),
    # ---------------------------------------------------------------- Delhi / Punjab / Chandigarh
    ("Delhi|New Delhi|Tis Hazari|Saket|Karkardooma|Rohini|Dwarka|Patiala House", "दिल्ली", "delhi"),
    ("Chandigarh", "चण्डीगढ़", "chandigarh"),
    ("Amritsar", "अमृतसर", "punjab"), ("Bathinda|Bhatinda", "बठिंडा", "punjab"),
    ("Faridkot", "फरीदकोट", "punjab"), ("Fatehgarh Sahib", "फतेहगढ़ साहिब", "punjab"),
    ("Fazilka", "फाजिल्का", "punjab"), ("Ferozepur|Firozpur", "फिरोजपुर", "punjab"),
    ("Gurdaspur", "गुरदासपुर", "punjab"), ("Hoshiarpur", "होशियारपुर", "punjab"),
    ("Jalandhar", "जालंधर", "punjab"), ("Kapurthala", "कपूरथला", "punjab"),
    ("Ludhiana", "लुधियाना", "punjab"), ("Mansa", "मानसा", "punjab"), ("Moga", "मोगा", "punjab"),
    ("Mohali|SAS Nagar", "मोहाली", "punjab"), ("Muktsar|Sri Muktsar Sahib", "मुक्तसर", "punjab"),
    ("Pathankot", "पठानकोट", "punjab"), ("Patiala", "पटियाला", "punjab"),
    ("Rupnagar|Ropar", "रूपनगर", "punjab"), ("Sangrur", "संगरूर", "punjab"),
    ("Tarn Taran", "तरनतारन", "punjab"), ("Barnala", "बरनाला", "punjab"),
    # ---------------------------------------------------------------- Maharashtra
    ("Mumbai|Bombay", "मुम्बई", "maharashtra"), ("Pune|Poona", "पुणे", "maharashtra"),
    ("Nagpur", "नागपुर", "maharashtra"), ("Nashik|Nasik", "नाशिक", "maharashtra"),
    ("Chhatrapati Sambhajinagar", "छत्रपति संभाजीनगर", "maharashtra"), ("Thane", "ठाणे", "maharashtra"),
    ("Solapur", "सोलापुर", "maharashtra"), ("Kolhapur", "कोल्हापुर", "maharashtra"),
    ("Akola", "अकोला", "maharashtra"), ("Jalgaon", "जलगांव", "maharashtra"),
    ("Latur", "लातूर", "maharashtra"), ("Nanded", "नांदेड़", "maharashtra"),
    ("Ahmednagar|Ahilyanagar", "अहमदनगर", "maharashtra"), ("Satara", "सातारा", "maharashtra"),
    ("Sangli", "सांगली", "maharashtra"), ("Chandrapur", "चंद्रपुर", "maharashtra"),
    ("Yavatmal", "यवतमाल", "maharashtra"), ("Wardha", "वर्धा", "maharashtra"),
    ("Dhule", "धुले", "maharashtra"), ("Beed", "बीड", "maharashtra"),
    ("Ratnagiri", "रत्नागिरी", "maharashtra"), ("Raigad|Alibag", "रायगड", "maharashtra"),
    # ---------------------------------------------------------------- Gujarat
    ("Ahmedabad", "अहमदाबाद", "gujarat"), ("Surat", "सूरत", "gujarat"),
    ("Vadodara|Baroda", "वडोदरा", "gujarat"), ("Rajkot", "राजकोट", "gujarat"),
    ("Bhavnagar", "भावनगर", "gujarat"), ("Jamnagar", "जामनगर", "gujarat"),
    ("Junagadh", "जूनागढ़", "gujarat"), ("Gandhinagar", "गांधीनगर", "gujarat"),
    ("Anand", "आणंद", "gujarat"), ("Kutch|Bhuj", "कच्छ", "gujarat"), ("Mehsana", "मेहसाणा", "gujarat"),
    ("Bharuch", "भरूच", "gujarat"), ("Navsari", "नवसारी", "gujarat"), ("Valsad", "वलसाड", "gujarat"),
    ("Godhra|Panchmahal", "गोधरा", "gujarat"), ("Palanpur|Banaskantha", "पालनपुर", "gujarat"),
    ("Amreli", "अमरेली", "gujarat"), ("Surendranagar", "सुरेंद्रनगर", "gujarat"),
    ("Nadiad|Kheda", "नडियाद", "gujarat"),
    # ---------------------------------------------------------------- Karnataka
    ("Bengaluru|Bangalore", "बेंगलुरु", "karnataka"), ("Mysuru|Mysore", "मैसूरु", "karnataka"),
    ("Mangaluru|Mangalore", "मंगलुरु", "karnataka"), ("Hubballi|Hubli", "हुबली", "karnataka"),
    ("Dharwad", "धारवाड़", "karnataka"), ("Belagavi|Belgaum", "बेलगावी", "karnataka"),
    ("Kalaburagi|Gulbarga", "कलबुर्गी", "karnataka"), ("Ballari|Bellary", "बल्लारी", "karnataka"),
    ("Shivamogga|Shimoga", "शिवमोग्गा", "karnataka"), ("Tumakuru|Tumkur", "तुमकुरु", "karnataka"),
    ("Davanagere", "दावणगेरे", "karnataka"), ("Vijayapura", "विजयपुरा", "karnataka"),
    ("Udupi", "उडुपी", "karnataka"), ("Hassan", "हासन", "karnataka"), ("Mandya", "मंड्या", "karnataka"),
    ("Raichur", "रायचूर", "karnataka"), ("Bidar", "बीदर", "karnataka"),
    # ---------------------------------------------------------------- Tamil Nadu
    ("Chennai|Madras", "चेन्नई", "tn"), ("Coimbatore", "कोयंबटूर", "tn"), ("Madurai", "मदुरै", "tn"),
    ("Tiruchirappalli|Trichy", "तिरुचिरापल्ली", "tn"), ("Salem", "सेलम", "tn"),
    ("Tirunelveli", "तिरुनेलवेली", "tn"), ("Vellore", "वेल्लोर", "tn"), ("Erode", "इरोड", "tn"),
    ("Thanjavur", "तंजावुर", "tn"), ("Thoothukudi|Tuticorin", "थूथुकुडी", "tn"),
    ("Kanchipuram", "कांचीपुरम", "tn"), ("Dindigul", "डिंडीगुल", "tn"),
    # ---------------------------------------------------------------- Telangana / Andhra
    ("Hyderabad|Secunderabad", "हैदराबाद", "telangana"), ("Warangal", "वारंगल", "telangana"),
    ("Karimnagar", "करीमनगर", "telangana"), ("Nizamabad", "निज़ामाबाद", "telangana"),
    ("Khammam", "खम्मम", "telangana"), ("Rangareddy|Ranga Reddy", "रंगारेड्डी", "telangana"),
    ("Nalgonda", "नलगोंडा", "telangana"), ("Mahabubnagar", "महबूबनगर", "telangana"),
    ("Adilabad", "आदिलाबाद", "telangana"), ("Sangareddy", "संगारेड्डी", "telangana"),
    ("Visakhapatnam|Vizag", "विशाखापत्तनम", "ap"), ("Vijayawada", "विजयवाड़ा", "ap"),
    ("Guntur", "गुंटूर", "ap"), ("Nellore", "नेल्लोर", "ap"), ("Kurnool", "कुरनूल", "ap"),
    ("Tirupati", "तिरुपति", "ap"), ("Kakinada", "काकीनाडा", "ap"), ("Anantapur", "अनंतपुर", "ap"),
    ("Kadapa", "कडप्पा", "ap"), ("Rajahmundry|Rajamahendravaram", "राजमुंदरी", "ap"),
    ("Ongole", "ओंगोल", "ap"), ("Eluru", "एलुरु", "ap"), ("Srikakulam", "श्रीकाकुलम", "ap"),
    ("Vizianagaram", "विजयनगरम", "ap"),
    # ---------------------------------------------------------------- West Bengal / Odisha
    ("Kolkata|Calcutta", "कोलकाता", "wb"), ("Howrah", "हावड़ा", "wb"), ("Asansol", "आसनसोल", "wb"),
    ("Durgapur", "दुर्गापुर", "wb"), ("Siliguri", "सिलीगुड़ी", "wb"), ("Darjeeling", "दार्जिलिंग", "wb"),
    ("Bardhaman|Burdwan", "बर्धमान", "wb"), ("Hooghly|Chinsurah", "हुगली", "wb"),
    ("Krishnanagar|Nadia", "कृष्णनगर", "wb"), ("Murshidabad|Berhampore", "मुर्शिदाबाद", "wb"),
    ("Malda", "मालदा", "wb"), ("Bankura", "बांकुड़ा", "wb"), ("Purulia", "पुरुलिया", "wb"),
    ("Jalpaiguri", "जलपाईगुड़ी", "wb"), ("Barasat", "बारासात", "wb"), ("Alipore", "अलीपुर", "wb"),
    ("Bhubaneswar", "भुवनेश्वर", "odisha"), ("Cuttack", "कटक", "odisha"), ("Puri", "पुरी", "odisha"),
    ("Sambalpur", "संबलपुर", "odisha"), ("Berhampur|Ganjam", "ब्रह्मपुर", "odisha"),
    ("Balasore|Baleshwar", "बालासोर", "odisha"), ("Rourkela|Sundargarh", "राउरकेला", "odisha"),
    ("Koraput", "कोरापुट", "odisha"), ("Baripada|Mayurbhanj", "बारीपदा", "odisha"),
    ("Bhadrak", "भद्रक", "odisha"), ("Angul", "अंगुल", "odisha"), ("Dhenkanal", "ढेंकनाल", "odisha"),
    ("Balangir|Bolangir", "बलांगीर", "odisha"),
    # ---------------------------------------------------------------- Kerala / Assam / J&K / Goa
    ("Thiruvananthapuram|Trivandrum", "तिरुवनंतपुरम", "kerala"), ("Ernakulam|Kochi|Cochin", "एर्नाकुलम", "kerala"),
    ("Kozhikode|Calicut", "कोझिकोड", "kerala"), ("Thrissur", "त्रिशूर", "kerala"),
    ("Kollam|Quilon", "कोल्लम", "kerala"), ("Kannur", "कन्नूर", "kerala"),
    ("Palakkad", "पलक्कड़", "kerala"), ("Malappuram", "मलप्पुरम", "kerala"),
    ("Alappuzha|Alleppey", "अलप्पुझा", "kerala"), ("Kottayam", "कोट्टायम", "kerala"),
    ("Guwahati|Kamrup", "गुवाहाटी", "assam"), ("Dibrugarh", "डिब्रूगढ़", "assam"),
    ("Silchar|Cachar", "सिलचर", "assam"), ("Jorhat", "जोरहाट", "assam"), ("Tezpur", "तेजपुर", "assam"),
    ("Srinagar", "श्रीनगर", "jk"), ("Jammu", "जम्मू", "jk"), ("Anantnag", "अनंतनाग", "jk"),
    ("Baramulla", "बारामूला", "jk"),
    ("Panaji|Panjim", "पणजी", "goa"), ("Margao|Madgaon", "मडगांव", "goa"),
    # ------------------------------------------- names that exist in more than one State
    # Kept so they are RECOGNISED as places (and converted between scripts), but
    # they deliberately resolve to no State — see the module docstring.
    ("Aurangabad", "औरंगाबाद", "?"), ("Bilaspur", "बिलासपुर", "?"), ("Hamirpur", "हमीरपुर", "?"),
    ("Pratapgarh", "प्रतापगढ़", "?"), ("Balrampur", "बलरामपुर", "?"), ("Bijapur", "बीजापुर", "?"),
    ("Raigarh", "रायगढ़", "?"), ("Amravati|Amaravati", "अमरावती", "?"), ("Ramgarh", "रामगढ़", "?"),
    ("Kishangarh", "किशनगढ़", "?"),
]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = s.replace("‌", "").replace("‍", "")
    return re.sub(r"\s+", " ", s).strip().lower()


class Place:
    __slots__ = ("en", "hi", "state")

    def __init__(self, en: str, hi: str, state: Optional[str]):
        self.en, self.hi, self.state = en, hi, state

    def name(self, lang: str) -> str:
        return self.hi if lang == "hi" else self.en

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Place({self.en!r}, {self.state!r})"


_INDEX: dict[str, Place] = {}
for _en, _hi, _st in _ROWS:
    _aliases = [a.strip() for a in _en.split("|") if a.strip()]
    _p = Place(_aliases[0], _hi, None if _st == "?" else _st)
    for _a in _aliases + [_hi]:
        _INDEX[_norm(_a)] = _p
# common Hindi spelling variants a keyboard produces
for _variant, _canon in {"इन्दौर": "इंदौर", "भिंड": "भिण्ड", "छिन्दवाड़ा": "छिंदवाड़ा",
                         "मण्डला": "मंडला", "खण्डवा": "खंडवा", "होशंगाबाद": "नर्मदापुरम",
                         "इलाहाबाद": "प्रयागराज", "फैजाबाद": "अयोध्या", "कानपुर": "कानपुर नगर",
                         "गुड़गांव": "गुरुग्राम", "नोएडा": "गौतम बुद्ध नगर", "बनारस": "वाराणसी",
                         "झाँसी": "झांसी", "रांची": "रांची", "राँची": "रांची", "मुंबई": "मुम्बई",
                         "जमशेदपुर": "पूर्वी सिंहभूम", "भिलाई": "दुर्ग", "अम्बिकापुर": "सरगुजा",
                         "जगदलपुर": "बस्तर", "हल्द्वानी": "नैनीताल", "आरा": "भोजपुर",
                         "मोतिहारी": "पूर्वी चम्पारण", "बेतिया": "पश्चिमी चम्पारण",
                         "सासाराम": "रोहतास", "छपरा": "सारण", "हाजीपुर": "वैशाली"}.items():
    if _norm(_canon) in _INDEX:
        _INDEX[_norm(_variant)] = _INDEX[_norm(_canon)]

_MAX_WORDS = max(len(k.split(" ")) for k in _INDEX)

# Place names that are also everyday words or common personal names ("Sagar
# Sharma", "sabzi mandi", "Anand", "Puri"). They are only trusted as a place when
# the brief marks them as one — after "district"/"जिला", beside a court word, or
# inside an address — never from a bare mention.
WEAK = {_norm(w) for w in (
    "Anand", "Sagar", "Hassan", "Salem", "Puri", "Pali", "Mandi", "Basti", "Sidhi", "Guna",
    "Dhar", "Panna", "Mau", "Una", "Gaya", "Banda", "Kota", "Moga", "Beed", "Jind", "Nuh",
    "Mansa", "Rampur", "Deeg", "Ara", "Saran", "Solan", "Durg", "Tonk", "Churu", "Sehore",
    "Harda", "Rewa", "Dewas", "Etah", "Mahoba", "Satara", "Latur", "Akola", "Jammu", "Nadiad",
    "सागर", "पाली", "मंडी", "मण्डी", "बस्ती", "सीधी", "गुना", "धार", "पन्ना", "मऊ", "ऊना", "गया",
    "बांदा", "कोटा", "आरा", "आणंद", "पुरी", "सेलम", "हासन", "डीग",
)}


def is_weak(matched_text: str) -> bool:
    return _norm(matched_text) in WEAK


def lookup(text: str) -> Optional[Place]:
    """Exact place lookup (either script, any listed alias)."""
    return _INDEX.get(_norm(text))


def find_places(text: str) -> list[tuple[int, int, Place]]:
    """Every place named in `text`, as (start, end, Place), longest match first at
    each position and never overlapping. Word-bounded, so "Una" never matches
    inside "Unnao" and "Mau" never inside "Mauganj"."""
    out: list[tuple[int, int, Place]] = []
    src = unicodedata.normalize("NFC", text or "")
    # letters only: the danda "।" and Devanagari digits sit inside U+0900–097F, and a
    # sentence-final "ग्वालियर।" must still be Gwalior
    words = [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z]+|[ऀ-ॣॱ-ॿ]+", src)]
    i = 0
    while i < len(words):
        hit = None
        for n in range(min(_MAX_WORDS, len(words) - i), 0, -1):
            s, e = words[i][0], words[i + n - 1][1]
            p = _INDEX.get(_norm(src[s:e]))
            if p is not None:
                hit = (s, e, p, n)
                break
        if hit:
            out.append(hit[:3])
            i += hit[3]
        else:
            i += 1
    return out


def state_name(key: Optional[str], lang: str) -> str:
    if not key or key not in STATES:
        return ""
    hi, en = STATES[key]
    return hi if lang == "hi" else en


def find_state(text: str) -> Optional[str]:
    """A State named outright in the brief ("Madhya Pradesh", "म.प्र.", "MP")."""
    src = unicodedata.normalize("NFC", text or "")
    # a State's name inside an institution's name is not the State: "Punjab
    # National Bank" put "(पंजाब)" on an Indore filing
    src = re.sub(r"(?:punjab|पंजाब)\s*(?:national|नेशनल|&|and|एंड)\s*(?:bank|बैंक|sind|सिंध)"
                 r"|(?:bank|बैंक)\s+(?:of|ऑफ|ऑफ़)\s+(?:maharashtra|महाराष्ट्र|rajasthan|राजस्थान|bihar|बिहार)"
                 r"|(?:state\s+bank|स्टेट\s+बैंक)\s+(?:of|ऑफ)\s+[a-zऀ-ॿ]+"
                 r"|(?:[a-zऀ-ॿ]+\s+)?(?:gramin|ग्रामीण)\s+(?:bank|बैंक)"
                 r"|(?:uttar\s+pradesh|madhya\s+pradesh|उत्तर\s*प्रदेश|मध्य\s*प्रदेश)\s+(?:gramin|ग्रामीण|state\s+(?:road|electricity)|राज्य\s+(?:सड़क|विद्युत))",
                 " ", src, flags=re.I)
    low = _norm(src)
    for alias, key in sorted(_STATE_ALIASES.items(), key=lambda kv: -len(kv[0])):
        a = _norm(alias)
        if re.search(r"(?<![a-zऀ-ॣॱ-ॿ])" + re.escape(a) + r"(?![a-zऀ-ॣॱ-ॿ])", low):
            return key
    for abbr, key in _STATE_ABBR_CASED.items():
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(abbr) + r"(?![A-Za-z0-9])", src):
            return key
    return None
