"""CSS/role-селекторы для LinkedIn Jobs.

ВАЖНО: LinkedIn часто меняет вёрстку и классы (обфусцированные имена).
Поэтому для каждого элемента указано несколько запасных селекторов.
Если бот перестанет находить элемент, в первую очередь правят этот файл.
"""


class LinkedInSelectors:
    # --- Логин ---
    # Признаки того, что мы авторизованы (видна верхняя навигация с иконкой "Me").
    LOGGED_IN_NAV = 'nav.global-nav, header.global-nav, [data-test-global-nav]'
    LOGGED_IN_ME = 'button.global-nav__primary-link-me-menu-trigger, [data-control-name="nav.settings"]'
    # Поле логина на странице входа (признак, что мы НЕ авторизованы).
    LOGIN_USERNAME_INPUT = 'input#username, input[name="session_key"]'

    # --- Карточки вакансий в списке ---
    JOB_CARD = (
        'div.job-card-container, '
        'li.jobs-search-results__list-item, '
        'div.jobs-search-results__list-item, '
        '[data-job-id]'
    )
    # Ссылка на вакансию внутри карточки (содержит /jobs/view/).
    JOB_CARD_LINK = (
        'a.job-card-container__link, '
        'a.job-card-list__title, '
        'a[href*="/jobs/view/"]'
    )
    # Запасной общий селектор всех ссылок на вакансии.
    JOB_LINK_GENERIC = 'a[href*="/jobs/view/"]'

    # --- Страница вакансии ---
    VACANCY_TITLE = (
        'h1.jobs-unified-top-card__job-title, '
        'h1.job-details-jobs-unified-top-card__job-title, '
        'h1.t-24, '
        'h1'
    )

    # Триггер Easy Apply. Поддерживаем и классический UI (button.jobs-apply-button),
    # и новый SDUI-флоу, где это ссылка на /apply/ с подписью "Простая подача заявки".
    # Подписи учитываем на русском и английском.
    EASY_APPLY_TRIGGER = (
        'a[href*="/apply/"][href*="openSDUIApplyFlow"], '
        'button[aria-label*="Простая подача"], '
        'a[aria-label*="Простая подача"], '
        'button[aria-label*="Easy Apply" i], '
        'a[aria-label*="Easy Apply" i], '
        'button:has-text("Простая подача заявки"), '
        'a:has-text("Простая подача заявки"), '
        'button:has-text("Easy Apply"), '
        'button.jobs-apply-button'
    )

    # Признак, что отклик уже отправлен.
    ALREADY_APPLIED_TEXT = [
        "Заявка отправлена",
        "Вы откликнулись",
        "Отклик отправлен",
        "Applied",
        "Application submitted",
    ]

    # --- Форма Easy Apply (модалка или отдельная страница /apply/) ---
    # Стабильные test-хуки LinkedIn не зависят от языка интерфейса — ставим их первыми.
    SUBMIT_BUTTON = (
        'button[data-live-test-easy-apply-submit-button], '
        'button[aria-label*="Отправить заявку"], '
        'button:has-text("Отправить заявку"), '
        'button[aria-label="Submit application"], '
        'button:has-text("Submit application")'
    )
    NEXT_BUTTON = (
        'button[data-live-test-easy-apply-next-button], '
        'button[aria-label*="Continue to next"], '
        'button[aria-label*="Продолжить"], '
        'button:has-text("Далее"), '
        'button:has-text("Продолжить"), '
        'button:has-text("Next")'
    )
    REVIEW_BUTTON = (
        'button[data-live-test-easy-apply-review-button], '
        'button[aria-label*="Review"], '
        'button[aria-label*="Просмотрите"], '
        'button:has-text("Просмотреть"), '
        'button:has-text("Review")'
    )
    # Текстовое поле сопроводительного письма (появляется не всегда).
    COVER_LETTER_TEXTAREA = (
        'textarea[name*="coverLetter"], '
        'textarea[id*="coverLetter"], '
        'textarea[aria-label*="cover" i], '
        'textarea[aria-label*="сопроводительн" i]'
    )
    # Чекбокс "отслеживать компанию" (снимаем, если стоит).
    FOLLOW_COMPANY_CHECKBOX = (
        'input#follow-company-checkbox, '
        'label:has-text("Follow") input[type="checkbox"], '
        'label:has-text("Отслеживать") input[type="checkbox"]'
    )

    # --- Диалог подтверждения выхода из формы ---
    DISCARD_DIALOG = 'div[role="alertdialog"], div.artdeco-modal--confirm-dialog'
    DISCARD_BUTTON = (
        'button[data-control-name="discard_application_confirm_btn"], '
        'button:has-text("Discard"), '
        'button:has-text("Отменить")'
    )
    # Кнопка закрытия модального окна (крестик).
    DISMISS_BUTTON = (
        'button[aria-label="Dismiss"], '
        'button[aria-label="Закрыть"], '
        'button.artdeco-modal__dismiss'
    )
