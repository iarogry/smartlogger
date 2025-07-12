# -*- coding: utf-8 -*-
# ФАЙЛ: __manifest__.py для Odoo 17

{
    'name': "Huawei SmartLogger Integration",

    'summary': """
        Професійна інтеграція з Huawei FusionSolar API для множественних сонячних станцій (Odoo 17).
    """,

    'description': """

                                              Повнофункціональний модуль для інтеграції з Huawei FusionSolar API для Odoo 17:

                                              🔹 Підтримка множественних станцій з пагінацією
        🔹 Пакетна обробка для оптимізації API запитів  
        🔹 Розширена статистика та аналітика
        🔹 Автоматична синхронізація з налаштуваннями
        🔹 Інтелектуальна обробка помилок та повторні спроби
        🔹 Гнучкі налаштування продуктивності
        🔹 Автоматичне очищення історичних даних
        🔹 Детальна аналітика ефективності станцій
        🔹 Підтримка різних регіональних API endpoints
        🔹 Сучасний UI з Kanban, списками та формами

        **Нові можливості в Odoo 17:**
        - Покращений користувацький інтерфейс
        - Оптимізована продуктивність
        - Розширені можливості візуалізації
        - Краща інтеграція з системними компонентами

        Включає:
        - Автоматичну синхронізацію через Cron (кожні 15 хвилин)
        - Ручну синхронізацію через зручний майстер
        - Дашборд з аналітикою по всіх станціях
        - Історичні дані KPI з можливістю фільтрації
        - Розширені налаштування API для оптимізації
        - Захист від блокування API
        - Детальний моніторинг та логування
    """,

    'author': "Ярослав Гришин/HD Group LLC",
    'website': "https://www.hlibodar.com.ua",

    'category': 'Operations/IoT',
    'version': '17.0.2.0.0',  # Версия для Odoo 17

    # Залежності модуля для Odoo 17
    'depends': ['base', 'mail'],

    'data': [
        'security/ir.model.access.csv',
        'views/000_menu.xml',
        'data/config_data.xml',
        'views/smartlogger_config_views.xml',
        'views/smartlogger_action.xml',
        'views/smartlogger_additional_actions.xml',
        'views/smartlogger_data_views.xml',
        'views/smartlogger_station_views.xml',
        'views/smartlogger_dashboard_views.xml',
        'wizards/sync_data_wizard_views.xml',
        'data/cron_data.xml',
        'views/zzz_menu.xml',
    ],

    # Демо дані (опціонально)
    'demo': [
        # 'demo/demo_stations.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',

    # Додаткові характеристики для Odoo 17
    'images': ['static/descriptions/banner.png'],
    'price': 0,
    'currency': 'EUR',

    # Поддержка Odoo Enterprise features (если нужно)
    'support': 'https://www.hlibodar.com.ua',

    # Зовнішні залежності
    'external_dependencies': {
        'python': ['requests'],
    },

    # Додаткові мета-дані для Odoo 17
    'pre_init_hook': None,
    'post_init_hook': None,
    'uninstall_hook': None,

    # Клонування настроек (если нужно)
    'cloc_exclude': ['./**/*'],
}