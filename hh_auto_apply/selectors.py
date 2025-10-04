class Selectors:
    # --- Login ---
    LOGIN_PROFILE_LINK = '[data-qa="mainmenu_applicantProfile"]'
    LOGIN_RESUMES_LINK = 'a[href*="/applicant/resumes"]'
    LOGIN_PROFILE_ARIA = '[aria-label*="Профиль"]'

    # --- Vacancy List ---
    VACANCY_LIST_TITLE = '[data-qa="vacancy-serp__vacancy-title"]'
    VACANCY_LIST_TITLE_SERP = '[data-qa="serp-item__title"]'
    VACANCY_LIST_TITLE_BLOKO = 'a.bloko-link[data-qa*="title"]'
    VACANCY_LIST_WRAPPER = '[data-qa="vacancy-serp__vacancy"] , [data-qa="serp-item"]'
    VACANCY_LINK_IN_WRAPPER = 'a[href*="/vacancy/"]'
    VISIBLE_VACANCY_LINK = 'a[href*="/vacancy/"]:visible'

    # --- Vacancy Page ---
    APPLY_BUTTON_ROLE = 'button:has-text("Откликнуться")'
    APPLY_LINK_ROLE = 'link:has-text("Откликнуться")'
    APPLY_BUTTON_TOP = '[data-qa="vacancy-response-link-top"]'
    APPLY_BUTTON_SIDEBAR = '[data-qa="vacancy-sidebar-submit"]'
    ALREADY_APPLIED_TEXT = [
        "Отклик отправлен", "Вы откликнулись", "Отклик уже отправлен", "Отклик отправлен работодателю"
    ]
    VACANCY_TITLE_H1 = 'h1'
    VACANCY_TITLE_QA = '[data-qa="vacancy-title"]'
    VACANCY_TITLE_VIEW_QA = '[data-qa="vacancy-view-title"]'
    VACANCY_TITLE_CLASS = '.vacancy-title'

    # --- Apply Modal ---
    RESUME_SELECT_ITEM = '[data-qa="resume-select_item"]'
    RESUME_SELECT_ITEM_IN_GROUP = '[data-qa="resume-select"] [data-qa="resume-item"]'
    RESUME_GENERIC_QA = '[data-qa*="resume"]'
    RESUME_LABEL_WITH_TEXT = 'label:has-text("-")'
    RESUME_FALLBACK_INPUT = 'input[name="resume"]'
    RESUME_FALLBACK_RADIO = 'input[type="radio"][value*="resume"]'
    
    COVER_LETTER_TOGGLE = '[data-qa="vacancy-response-letter-toggle"]'
    COVER_LETTER_TEXTAREA = 'textarea[data-qa="vacancy-response-letter-input"]'
    COVER_LETTER_TEXTAREA_PLACEHOLDER = 'textarea[placeholder*="сопроводительное"]'
    COVER_LETTER_TEXTAREA_GENERIC = 'textarea'

    CONSENT_CHECKBOX_AGREEMENT = 'input[type="checkbox"][name*="agreement"]'
    CONSENT_CHECKBOX_QA = 'input[type="checkbox"][data-qa*="consent"]'
    CONSENT_CHECKBOX_REQUIRED = 'input[type="checkbox"][required]'

    SUBMIT_BUTTON = '[data-qa="vacancy-response-submit-button"]'
    SUBMIT_BUTTON_TEXT_1 = 'button:has-text("Отправить отклик")'
    SUBMIT_BUTTON_TEXT_2 = 'button:has-text("Отправить")'
    SUBMIT_BUTTON_GENERIC_QA = 'button[data-qa*="submit"]'
