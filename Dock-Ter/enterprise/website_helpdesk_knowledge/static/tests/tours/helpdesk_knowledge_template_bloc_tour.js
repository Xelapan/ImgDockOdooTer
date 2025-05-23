/** @odoo-module */

import tour from 'web_tour.tour';


tour.register('helpdesk_pick_template_as_message_from_knowledge', {
    url: '/web#action=helpdesk.helpdesk_ticket_action_main_tree',
    test: true,
}, [{ // click on the first record of the list
    trigger: 'tr.o_data_row:first-child .o_data_cell[name="name"]',
    run: 'click',
}, { // open an article
    trigger: 'button[title="Search Knowledge Articles"]',
    run: 'click',
}, { // click on the first command of the command palette
    trigger: '.o_command_palette_listbox #o_command_0',
    run: 'click',
}, { // wait for Knowledge to open
    trigger: '.o_knowledge_form_view',
}, { // click on the "Send as Message" button from the template block
    trigger: '.o_knowledge_behavior_type_template .o_knowledge_toolbar_button_text:contains("Send as Message")',
    run: 'click',
}, { // check that the content of the template block has been added to the mail composer
    trigger: '.o_mail_composer_form .o_field_html p:contains("Hello world")',
}, { // cancel the message, no need to send it and trigger a backend `write` (see discuss tests for that)
    trigger: 'footer button:contains(Cancel)',
    run: 'click',
}, ...tour.stepUtils.discardForm(),
]);

tour.register('helpdesk_pick_template_as_description_from_knowledge', {
    url: '/web#action=helpdesk.helpdesk_ticket_action_main_tree',
    test: true,
}, [{ // click on the first record of the list
    trigger: 'tr.o_data_row:first-child .o_data_cell[name="name"]',
    run: 'click',
}, { // open an article
    trigger: 'button[title="Search Knowledge Articles"]',
    run: 'click',
}, { // click on the first command of the command palette
    trigger: '.o_command_palette_listbox #o_command_0',
    run: 'click',
}, { // wait for Knowledge to open
    trigger: '.o_knowledge_form_view',
}, { // click on the "Use as Description" button from the template block
    trigger: '.o_knowledge_behavior_type_template .o_knowledge_toolbar_button_text:contains("Use as Description")',
    run: 'click',
}, { // check that the description contains content of the template block
    trigger: '.o_form_sheet .o_field_html p:contains("Hello world")',
}, ...tour.stepUtils.discardForm(),
]);
