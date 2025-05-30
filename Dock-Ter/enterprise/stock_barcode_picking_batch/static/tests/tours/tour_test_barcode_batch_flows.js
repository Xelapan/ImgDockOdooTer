odoo.define('test_barcode_batch_flows.tour', function(require) {
'use strict';

const tour = require('web_tour.tour');
const helper = require('stock_barcode_picking_batch.tourHelper');

function checkState(state) {
    helper.assertLinesCount(state.linesCount);
    helper.assertScanMessage(state.scanMessage);
    helper.assertValidateVisible(state.validate.isVisible);
    helper.assertValidateIsHighlighted(state.validate.isHighlighted);
    helper.assertValidateEnabled(state.validate.isEnabled);
}

function updateState(oldState, newState) {
    const state = Object.assign({}, oldState, newState);
    state.validate = Object.assign({}, oldState.validate, newState.validate);
    return state;
}

const defaultViewState = {
    linesCount: 0,
    scanMessage: '',
    validate: {
        isEnabled: true,
        isHighlighted: false,
        isVisible: true,
    },
};
let currentViewState;

// ----------------------------------------------------------------------------
// Tours
// ----------------------------------------------------------------------------
tour.register('test_barcode_batch_receipt_1', {test: true}, [
    {
        trigger: '.o_barcode_client_action',
        run: function () {
            currentViewState = updateState(defaultViewState, {
                linesCount: 5, // 6 move lines but 5 visibles as tracked by SN lines are grouped.
                scanMessage: 'scan_product',
                validate: {
                    isEnabled: true,
                    isVisible: true,
                },
            });
            checkState(currentViewState);
            const $linesFromFirstPicking = $(helper.getLines({index: [1, 5]}));
            const $linesFromSecondPicking = $(helper.getLines({from: 2, to: 3}));
            const $linesFromThirdPicking = $(helper.getLines({index: 4}));
            helper.assertLinesBelongTo($linesFromFirstPicking, 'picking_receipt_1');
            helper.assertLinesBelongTo($linesFromSecondPicking, 'picking_receipt_2');
            helper.assertLinesBelongTo($linesFromThirdPicking, 'picking_receipt_3');
        },
    },
    // Unfolds grouped lines for product tracked by SN.
    { trigger: '.o_line_button.o_toggle_sublines' },
    {
        trigger: '.o_sublines .o_barcode_line',
        run: function () {
            const sublines = document.querySelectorAll('.o_sublines .o_barcode_line');
            helper.assert(sublines.length, 2, 'it should have 2 sublines');
        }
    },

    //Check show information.
    {
        trigger: '.o_show_information',
    },
    {
        trigger: '.o_form_label:contains("State")',
    },
    {
        trigger: '.o_close',
    },

    // Scan product1 x4
    {
        trigger: '.o_barcode_client_action',
        run: 'scan product1'
    },
    {
        trigger: '.o_barcode_line:first-child.o_selected.o_line_completed',
        run: function() {
            currentViewState.scanMessage = 'scan_product_or_dest';
            checkState(currentViewState);
            const $lines =  helper.getLines({barcode: 'product1'});
            helper.assert($lines.length, 2, "Expect 2 lines for product1");
            helper.assertLineIsHighlighted($($lines[0]), true);
            helper.assertLineQty($($lines[0]), '1');
            helper.assertLineQty($($lines[1]), '0');
        }
    },

    {
        trigger: '.o_barcode_client_action',
        run: 'scan product1'
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan product1'
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan product1'
    },
    {
        trigger: '.o_barcode_line[data-barcode="product1"] .qty-done:contains("3")',
        run: function() {
            checkState(currentViewState);
            const $lines =  helper.getLines({barcode: 'product1'});
            helper.assert($lines.length, 2, "Expect 2 lines for product1");
            helper.assertLineIsHighlightedGreen($lines, true);
            helper.assertLineQty($($lines[0]), '1');
            helper.assertLineQty($($lines[1]), '3');
        }
    },

    // Scan one more time the product1 -> As no more quantity is expected, it must create
    // a new line and it will take the picking id of the selected line (here, 'picking_receipt_2').
    {
        trigger: '.o_barcode_client_action',
        run: 'scan product1'
    },
    {
        trigger: '.o_barcode_line:nth-child(6)',
        run: function() {
            currentViewState.linesCount = 6;
            checkState(currentViewState);
            const $lines =  helper.getLines({barcode: 'product1'});
            helper.assert($lines.length, 3, "Expect 3 lines for product1");
            const $line1 = $($lines[0]);
            const $line2 = $($lines[1]);
            const $line3 = $($lines[2]);
            helper.assertLineQty($line1, '1'); // First product1 line:  qty 1/1
            helper.assertLineIsHighlighted($line1, false);
            helper.assertLineQty($line2, '3'); // Second product1 line: qty 3/3
            helper.assertLineIsHighlighted($line2, false);
            helper.assertLineQty($line3, '1'); // Last added line:      qty 1
            helper.assertLineIsHighlightedGreen($line3, true);
            helper.assert($line3.find('.o_picking_label').text(), 'picking_receipt_2');
        }
    },

    // Scan productserial1
    {
        trigger: '.o_barcode_client_action',
        run: 'scan productserial1'
    },
    {
        trigger: '.o_barcode_line:nth-child(6).o_highlight[data-barcode="productserial1"]',
        run: function() {
            currentViewState.scanMessage = 'scan_serial';
            checkState(currentViewState);
            const sublines = document.querySelectorAll('.o_barcode_line.o_selected .o_sublines .o_barcode_line');
            helper.assert(sublines.length, 2);
            helper.assertLineQty($(sublines[0]), '0');
            helper.assertLineIsHighlighted($(sublines[0]), true);
            helper.assertLineQty($(sublines[1]), '0');
            helper.assertLineIsHighlighted($(sublines[1]), false);
        }
    },

    // Scan two serial numbers
    {
        trigger: '.o_barcode_client_action',
        run: 'scan SN-LHOOQ'
    },
    {
        trigger: '.o_barcode_line.o_highlight[data-barcode="productserial1"]:contains("SN-LHOOQ")',
        run: function() {
            currentViewState.scanMessage = 'scan_serial';
            checkState(currentViewState);
            const sublines = document.querySelectorAll('.o_sublines [data-barcode=productserial1]');
            helper.assert(sublines.length, 2, "Expect 2 lines for productserial1");
            helper.assertLineQty($(sublines[0]), '1');
            helper.assertLineQty($(sublines[1]), '0');
        }
    },
    // Scan the same serial number -> Should show an warning message.
    {
        trigger: '.o_barcode_client_action',
        run: 'scan SN-LHOOQ'
    },
    {
        trigger: '.o_notification.border-danger'
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan SN-OQPAPT'
    },
    {
        trigger: '.o_barcode_line.o_highlight[data-barcode="productserial1"]:contains("SN-OQPAPT")',
        run: function() {
            currentViewState.scanMessage = 'scan_product_or_dest';
            checkState(currentViewState);
            const sublines = document.querySelectorAll('.o_sublines [data-barcode=productserial1]');
            helper.assert(sublines.length, 2, "Expect 2 lines for productserial1");
            helper.assertLineQty($(sublines[0]), '1');
            helper.assertLineQty($(sublines[1]), '1');
        }
    },

    // Scan productlot1
    {
        trigger: '.o_barcode_client_action',
        run: 'scan productlot1'
    },
    {
        trigger: '.o_barcode_line.o_highlight[data-barcode="productlot1"]',
        run: function() {
            currentViewState.scanMessage = 'scan_lot';
            checkState(currentViewState);
            const $lines =  helper.getLines({barcode: 'productlot1'});
            helper.assert($lines.length, 2, "Expect 2 lines for productlot1");
            const $line1 = $($lines[0]);
            const $line2 = $($lines[1]);
            helper.assertLineQty($line1, '0');
            helper.assertLineIsHighlighted($line1, true);
            helper.assert($line1.find('.o_picking_label').text(), 'picking_receipt_2');
            helper.assertLineQty($line2, '0');
            helper.assertLineIsHighlighted($line2, false);
            helper.assert($line2.find('.o_picking_label').text(), 'picking_receipt_3');
        }
    },

    // Scan lot0001 x4
    {
        trigger: '.o_barcode_client_action',
        run: 'scan lot0001'
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan lot0001'
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan lot0001'
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan lot0001'
    },
    {
        trigger: '.o_barcode_line.o_highlight .qty-done:contains("4")',
        run: function() {
            currentViewState.scanMessage = 'scan_lot';
            checkState(currentViewState);
            const $lines =  helper.getLines({barcode: 'productlot1'});
            helper.assert($lines.length, 2, "Expect 2 lines for productlot1");
            const $line1 = $($lines[0]);
            const $line2 = $($lines[1]);
            helper.assertLineQty($line1, '4');
            helper.assertLineIsHighlighted($line1, true);
            helper.assert($line1.find('.o_picking_label').text(), 'picking_receipt_2');
            helper.assertLineQty($line2, '0');
            helper.assertLineIsHighlighted($line2, false);
            helper.assert($line2.find('.o_picking_label').text(), 'picking_receipt_3');
        },
    },
    // Open the view to add a line and close it immediately.
    {
        trigger: '.o_add_line',
    },
    {
        trigger: '.o_discard',
    },
    {
        trigger: '.o_validate_page',
        run: function() {
            checkState(currentViewState);
        },
    },

    // Create a new line for productlot1 with an another lot name...
    {
        trigger: '.o_add_line',
    },
    {
        trigger: ".o_field_widget[name=product_id] input",
        run: 'text productlot1',
    },
    {
        trigger: ".ui-menu-item > a:contains('productlot1')",
    },
    {
        trigger: ".o_field_widget[name=qty_done] input",
        run: 'text 0',
    },
    {
        trigger: ".o_field_widget[name=picking_id] input",
        run: 'text picking_receipt_2',
    },
    {
        trigger: ".ui-menu-item > a:contains('picking_receipt_2')",
    },
    {
        trigger: '.o_save',
    },
    { trigger: '.o_barcode_line.o_selected .btn.o_toggle_sublines .fa-caret-down' },
    { trigger: '.o_sublines .o_barcode_line:nth-child(2)' },
    {
        trigger: '.o_sublines .o_barcode_line:nth-child(2).o_selected',
        run: function() {
            checkState(currentViewState);
            const groupLines =  document.querySelectorAll('.o_barcode_lines > [data-barcode=productlot1]');
            helper.assert(groupLines.length, 2, "Expect 2 lines for productlot1");
            const sublines = document.querySelectorAll('.o_sublines [data-barcode=productlot1]');
            helper.assert(sublines.length, 2, "Expect 2 sublines for productlot1");
            helper.assertLineQty($(sublines[0]), '4'); // Previous line (4/8).
            helper.assertLineIsHighlighted($(sublines[0]), false);
            helper.assertLineQty($(sublines[1]), '0'); // New created line.
            helper.assertLineIsHighlighted($(sublines[1]), true);
        },
    },

    // Scans lot0002 x4
    { trigger: '.o_barcode_client_action', run: 'scan lot0002' },
    { trigger: '.o_barcode_client_action', run: 'scan lot0002' },
    { trigger: '.o_barcode_client_action', run: 'scan lot0002' },
    { trigger: '.o_barcode_client_action', run: 'scan lot0002' },
    {
        trigger: '.o_sublines .o_barcode_line.o_highlight:contains("lot0002") .qty-done:contains("4")',
        run: function() {
            const sublines = document.querySelectorAll('.o_sublines [data-barcode=productlot1]');
            helper.assert(sublines.length, 2, "Expect 2 lines for productlot1");
            helper.assertLineQty($(sublines[0]), '4');
            helper.assertLineIsHighlighted($(sublines[0]), false);
            helper.assertLineQty($(sublines[1]), '4');
            helper.assertLineIsHighlighted($(sublines[1]), true);
        }
    },
    // Scan again the same lot0002 x4, it should select and increment the empty line.
    { trigger: '.o_barcode_client_action', run: 'scan lot0002' },
    { trigger: '.o_barcode_client_action', run: 'scan lot0002' },
    { trigger: '.o_barcode_client_action', run: 'scan lot0002' },
    { trigger: '.o_barcode_client_action', run: 'scan lot0002' },
    {
        trigger: '.o_barcode_line.o_highlight:contains("lot0002"):contains("picking_receipt_3") .qty-done:contains("4")',
        run: function() {
            currentViewState.validate.isHighlighted = true;
            currentViewState.scanMessage = 'scan_product_or_dest';
            currentViewState.validate.isHighlighted = true;
            checkState(currentViewState);
            const lines =  document.querySelectorAll('.o_barcode_lines > [data-barcode=productlot1]');
            helper.assert(lines.length, 2, "Expect 2 lines for productlot1");
            const $line1 = $(lines[0]);
            const $line2 = $(lines[1]);
            helper.assertLineQty($line1, '8');
            helper.assertLineIsHighlighted($line1, false);
            helper.assert($line1.find('.o_picking_label').text(), 'picking_receipt_2');
            helper.assertLineQty($line2, '4');
            helper.assertLineIsHighlighted($line2, true);
            helper.assert($line2.find('.o_picking_label').text(), 'picking_receipt_3');
        }
    },
    // Selects the subline with the lot0002 and scans it again, it should increment the selected line.
    { trigger: '.o_sublines .o_barcode_line:contains("lot0002")' },
    {
        trigger: '.o_sublines .o_selected:contains("lot0002")',
        run: 'scan lot0002'
    },
    {
        trigger: '.o_sublines .o_barcode_line.o_highlight:contains("lot0002") .qty-done:contains("5")',
        run: function() {
            const sublines = document.querySelectorAll('.o_sublines [data-barcode=productlot1]');
            helper.assert(sublines.length, 2, "Expect 2 lines for productlot1");
            helper.assertLineQty($(sublines[0]), '4');
            helper.assertLineIsHighlighted($(sublines[0]), false);
            helper.assertLineQty($(sublines[1]), '5');
            helper.assertLineIsHighlighted($(sublines[1]), true);
        }
    },
]);

tour.register('test_barcode_batch_delivery_1', {test: true}, [
    {
        trigger: '.o_barcode_client_action',
        run: function () {
            currentViewState = updateState(defaultViewState, {
                linesCount: 10,
                scanMessage: 'scan_src',
            });
            checkState(currentViewState);
            const lines = document.querySelectorAll('.o_barcode_line')

            // Products comming from Section 1.
            helper.assertLineLocations(lines[0], '.../Section 1');
            helper.assertLineProduct(lines[0], 'product1');

            helper.assertLineLocations(lines[1], '.../Section 1');
            helper.assertLineProduct(lines[1], 'product1');

            helper.assertLineLocations(lines[2], '.../Section 1');
            helper.assertLineProduct(lines[2], 'product4');

            helper.assertLineLocations(lines[3], '.../Section 1');
            helper.assertLineProduct(lines[3], 'productserial1');
            helper.assert(lines[3].querySelector('.o_line_lot_name').innerText, 'sn1');

            // Products coming from Section 2.
            helper.assertLineLocations(lines[4], '.../Section 2');
            helper.assertLineProduct(lines[4], 'product2');

            // Products coming from Section 3.
            helper.assertLineLocations(lines[5], '.../Section 3');
            helper.assertLineProduct(lines[5], 'product2');

            helper.assertLineLocations(lines[6], '.../Section 3');
            helper.assertLineProduct(lines[6], 'product3');

            // Products coming from Section 4.
            helper.assertLineLocations(lines[7], '.../Section 4');
            helper.assertLineProduct(lines[7], 'product4');

            // Products coming from Section 5.
            helper.assertLineLocations(lines[8], '.../Section 5');
            helper.assertLineProduct(lines[8], 'product5');

            helper.assertLineLocations(lines[9], '.../Section 5');
            helper.assertLineProduct(lines[9], 'product5');

            // Checks each line belong to the right picking.
            helper.assertLinesBelongTo($([lines[0], lines[4], lines[5]]), 'picking_delivery_1');
            helper.assertLinesBelongTo($([lines[1], lines[2], lines[6], lines[7]]), 'picking_delivery_2');
            helper.assertLinesBelongTo($([lines[8], lines[9]]), 'picking_delivery_package');
            helper.assertLineBelongTo($(lines[3]), 'picking_delivery_sn');
        },
    },
    // Scans the source (Section 1) then scans product1 x2, product4 x1
    { trigger: '.o_barcode_client_action', run: 'scan LOC-01-01-00' },
    {
        trigger: '.o_scan_message.o_scan_product',
        extra_trigger: '.o_barcode_line .o_line_source_location:contains(".../Section 1") .fw-bold',
        run: 'scan product1'
    },
    {
        trigger: '.o_barcode_line:first-child.o_line_completed ',
        run: 'scan product1'
    },
    {
        trigger: '.o_barcode_line:nth-child(2).o_line_completed ',
        run: 'scan product4'
    },

    // Scan wrong SN.
    {
        trigger: '.o_barcode_line:nth-child(3).o_line_completed ',
        run: 'scan sn2'
    },

    // Scans the next source (Section 2)
    {
        trigger: '.o_scan_message.o_scan_product_or_src',
        extra_trigger: '.o_barcode_line:nth-child(4).o_line_completed ',
        run: 'scan LOC-01-02-00'
    },
    // Scan product2 x2
    {
        trigger: '.o_barcode_line .o_line_source_location:contains(".../Section 2") .fw-bold',
        run: 'scan product2' // Must complete the line from Section 2.
    },
    {
        trigger: '.o_barcode_line:nth-child(5).o_selected.o_line_completed',
        run: function() {
            const lines = document.querySelectorAll('.o_barcode_line');
            helper.assertLineBelongTo($('.o_barcode_line:nth-child(5)'), 'picking_delivery_1');
            helper.assertLineLocations(lines[4], '.../Section 2');
            helper.assertLineBelongTo($('.o_barcode_line:nth-child(6)'), 'picking_delivery_1');
            helper.assertLineLocations(lines[5], '.../Section 3');
        }
    },
    // Scans again product2 but it's reserved in Section 3 and we're still in Section 2 and scaning
    // the location is mandatory. So the application should ask to scan the location to confirm.
    { trigger: ".o_barcode_client_action", run: "scan product2" },
    {
        trigger: ".o_notification.border-danger:contains('Scan the current location to confirm that.')",
        run: "scan LOC-01-02-00",
    },
    { trigger: ".o_barcode_client_action", run: "scan product2" },
    {
        trigger: '.o_barcode_line:nth-child(6).o_selected.o_line_completed .product-label:contains("product2")',
        run: function () {
            currentViewState.scanMessage = 'scan_product_or_src';
            checkState(currentViewState);
            const lines = document.querySelectorAll('.o_barcode_line');
            helper.assertLineBelongTo($('.o_barcode_line:nth-child(5)'), 'picking_delivery_1');
            helper.assertLineLocations(lines[4], '.../Section 2');
            helper.assertLineBelongTo($('.o_barcode_line:nth-child(6)'), 'picking_delivery_1');
            helper.assertLineLocations(lines[5], '.../Section 2');
        },
    },

    // Scans next source location (Section 3)
    {
        trigger: '.o_barcode_client_action',
        run: 'scan shelf3'
    },

    // Scan product3 x2
    { trigger: '.o_scan_message.o_scan_product', run: 'scan product3' },
    { trigger: '.o_barcode_line:nth-child(7).o_selected', run: 'scan product3' },

    // Change the location for shelf 4.// Scans next source location (Section 3)
    {
        trigger: '.o_barcode_line:nth-child(7).o_line_completed.o_selected',
        run: 'scan shelf4'
    },

    // Scan product4 x1
    {
        trigger: '.o_barcode_line .o_line_source_location:contains(".../Section 4") .fw-bold',
        run: 'scan product4'
    },

    // Change the location for shelf 5 (the last one).
    {
        trigger: '.o_barcode_line:nth-child(8).o_line_completed.o_selected',
        run: 'scan shelf5'
    },

    // Scan p5pack01 which is attended.
    {
        trigger: '.o_barcode_line .o_line_source_location:contains(".../Section 5") .fw-bold',
        run: 'scan p5pack01'
    },
    // Scan p5pack02 which isn't attended.
    {
        trigger: '.o_barcode_client_action',
        run: 'scan p5pack02'
    },

    {
        trigger: '.o_barcode_line:contains("p5pack02")',
        run: function () {
            currentViewState.linesCount = 11;
            currentViewState.scanMessage = 'scan_product_or_src';
            checkState(currentViewState);
            const lines = document.querySelectorAll('.o_barcode_line');
            const line1 = lines[8]; // no pack, qty 0/4
            const line2 = lines[9]; // p5pack01, qty 4/4
            const line3 = lines[10]; // p5pack02, qty 4
            helper.assertLineQuantityOnReservedQty(8, '0 / 4');
            helper.assertLineQuantityOnReservedQty(9, '4 / 4');
            helper.assertLineQuantityOnReservedQty(10, '4');
            helper.assert(line1.querySelector('[name="package"]>span').innerText, "p5pack01 ?");
            helper.assert(line2.querySelector('[name="package"]>span').innerText, "p5pack01");
            helper.assert(line3.querySelector('[name="package"]>span').innerText, "p5pack02");
        },
    },
    { trigger: '.o_validate_page' },
    { trigger: '.btn-primary[name="process_cancel_backorder"]' },
    { trigger: '.o_notification.border-success' },
]);

tour.register('test_barcode_batch_delivery_2_move_entire_package', {test: true}, [
    // Should have 3 lines: 2 for product2 (one by picking) and 1 for the package pack1.
    {
        trigger: '.o_barcode_client_action',
        run: function() {
            helper.assertScanMessage('scan_product_or_package');
            const lines = document.querySelectorAll('.o_barcode_line');
            // Line for product2, delivery 1.
            helper.assertLineBelongTo($(lines[0]), 'delivery_1');
            helper.assertButtonIsVisible($(lines[0]), 'package_content', false);
            helper.assertLineQuantityOnReservedQty(0, '0 / 5');
            // Line for product2, delivery 2.
            helper.assertLineBelongTo($(lines[1]), 'delivery_2');
            helper.assertButtonIsVisible($(lines[1]), 'package_content', false);
            helper.assertLineQuantityOnReservedQty(1, '0 / 5');
            // Package line for delivery 1.
            helper.assertLineBelongTo($(lines[2]), 'delivery_1');
            helper.assertButtonIsVisible($(lines[2]), 'package_content');
            helper.assertLineQuantityOnReservedQty(2, '0 / 1');
        }
    },

    // Scans pack1 => Completes the corresponding package line.
    { trigger: '.o_barcode_client_action', run: 'scan pack1' },
    {
        trigger: '.o_barcode_line:nth-child(3).o_line_completed',
        run: function() {
            helper.assertLineQuantityOnReservedQty(2, '1 / 1');
        }
    },

    // Scans pack2 => Completes the two lines waiting for it.
    { trigger: '.o_barcode_client_action', run: 'scan pack2' },
    {
        trigger: '.o_barcode_line.o_selected:nth-child(1)',
        extra_trigger: '.o_barcode_line.o_selected:nth-child(2)',
        run: function() {
            helper.assertLineQuantityOnReservedQty(0, '5 / 5');
            helper.assertLineQuantityOnReservedQty(1, '5 / 5');
        }
    },
]);

tour.register('test_barcode_batch_scan_lots', {test: true}, [
    // RECEIPT PART:
    // Open the batch receipt by scanning it.
    { trigger: '.o_stock_barcode_main_menu', run: 'scan test_barcode_batch_scan_lots - receipt' },
    // Scan productlot1 then 3x lot1
    { trigger: '.o_barcode_line', run: 'scan productlot1' },
    { trigger: '.o_barcode_line.o_selected', run: 'scan lot1' },
    { trigger: '.o_barcode_line.o_selected', run: 'scan lot1' },
    { trigger: '.o_barcode_line.o_selected', run: 'scan lot1' },
    {
        trigger: '.o_barcode_line.o_selected .qty-done:contains(3)',
        run: function () {
            const $lines = helper.getLines();
            const [$line1, $line2] = [$($lines[0]), $($lines[1])];
            helper.assertLineBelongTo($line1, "receipt_1");
            helper.assertLineBelongTo($line2, "receipt_2");
            helper.assertLineQty($line1, "3");
            helper.assertLineQty($line2, "0");
        },
    },
    // Now scan 1x lot2. It should create a new line for receipt_1 since the line is uncompleted.
    { trigger: '.o_barcode_client_action', run: 'scan lot2' },
    // Scan again 2x lot2. It should increment the receipt_2 line now the receipt_1 line is complete
    { trigger: '.o_barcode_line.o_selected.o_line_completed', run: 'scan lot2' },
    { trigger: '.o_barcode_line.o_selected:not(.o_line_completed)', run: 'scan lot2' },
    {
        trigger: '.o_barcode_line.o_selected .qty-done:contains(2)',
        run: function () {
            const $lines = helper.getLines();
            const [$line1, $line2] = [$($lines[0]), $($lines[1])];
            helper.assertLineBelongTo($line1, "receipt_1");
            helper.assertLineBelongTo($line2, "receipt_2");
            helper.assertLineQty($line1, "4");
            helper.assertLineQty($line2, "2");
        },
    },
    // Scan 2x lot3 to complete the batch.
    { trigger: '.o_barcode_client_action', run: 'scan lot3' },
    { trigger: '.o_barcode_client_action', run: 'scan lot3' },
    { trigger: '.o_barcode_line.o_selected.o_line_completed .o_line_button.o_toggle_sublines' },
    {
        trigger: '.o_barcode_line.o_selected.o_line_completed .o_sublines',
        run: function () {
            const $lines = helper.getLines();
            const [$line1, $line2] = [$($lines[0]), $($lines[1])];
            const [$subline1, $subline2] = [$($lines[2]), $($lines[3])];
            helper.assertLineBelongTo($line1, "receipt_1");
            helper.assertLineBelongTo($line2, "receipt_2");
            helper.assertLineQty($line1, "4");
            helper.assertLineQty($line2, "4");
            helper.assertLineQty($subline1, "2");
            helper.assertLineQty($subline2, "2");
        },
    },
    { trigger: '.o_barcode_client_action', run: 'scan O-BTN.validate' },
    { trigger: '.o_notification.border-success' },

    // DELIVERY PART:
    // Now, open the batch delivery.
    { trigger: '.o_stock_barcode_main_menu', run: 'scan test_barcode_batch_scan_lots - delivery' },
    {
        trigger: '.o_barcode_line',
        run: function () {
            const $lines = helper.getLines();
            const [$line1, $line2] = [$($lines[0]), $($lines[1])];
            helper.assertLineBelongTo($line1, "delivery_1");
            helper.assertLineBelongTo($line2, "delivery_2");
            helper.assertLineQty($line1, "0");
            helper.assertLineQty($line2, "0");
            helper.assert($line1.find('.o_line_lot_name').text(), 'lot1');
            helper.assert($line2.find('.o_line_lot_name').text(), 'lot2');
        },
    },
    // First, scan productlot1. The first line (for delivery_1) should be selected.
    { trigger: '.o_barcode_client_action', run: 'scan productlot1' },
    // Then, scan lot which is reserved for delivery_2 but will be assigned to
    // delivery_1 since it's its line who is selected.
    { trigger: '.o_barcode_line.o_selected', run: 'scan lot2' },
    // Then, scan lot3 which isn't reserved and scan again lot2 to complete delivery_1.
    { trigger: '.o_barcode_line.o_selected', run: 'scan lot3' },
    { trigger: '.o_barcode_line.o_selected', run: 'scan lot2' },
    { trigger: '.o_barcode_line.o_selected.o_line_completed .o_line_button.o_toggle_sublines' },
    {
        trigger: '.o_barcode_line.o_selected.o_line_completed .o_sublines',
        run: function () {
            const $lines = helper.getLines();
            const [$line1, $line2] = [$($lines[0]), $($lines[3])];
            const [$subline1, $subline2] = [$($lines[1]), $($lines[2])];
            helper.assertLineBelongTo($line1, "delivery_1");
            helper.assertLineBelongTo($line2, "delivery_2");
            helper.assertLineQty($line1, "3");
            helper.assertLineQty($line2, "0");
            helper.assertLineQty($subline1, "2");
            helper.assertLineQty($subline2, "1");
            helper.assert($subline1.find('.o_line_lot_name').text(), 'lot2');
            helper.assert($subline2.find('.o_line_lot_name').text(), 'lot3');
        },
    },
    // Scan lot1, lot2 and lot3 to complete delivery_2.
    { trigger: '.o_barcode_client_action', run: 'scan lot2' },
    { trigger: '.o_barcode_line.o_selected:not(.o_line_completed)', run: 'scan lot1' },
    { trigger: '.o_barcode_client_action', run: 'scan lot3' },
    { trigger: '.o_barcode_line.o_selected.o_line_completed .o_line_button.o_toggle_sublines' },
    {
        trigger: '.o_barcode_line.o_selected.o_line_completed .o_sublines',
        run: function () {
            const $lines = helper.getLines();
            const [$line1, $line2] = [$($lines[0]), $($lines[1])];
            const [$subline1, $subline2, $subline3] = [$($lines[2]), $($lines[3]), $($lines[4])];
            helper.assertLineBelongTo($line1, "delivery_1");
            helper.assertLineBelongTo($line2, "delivery_2");
            helper.assertLineQty($line1, "3");
            helper.assertLineQty($line2, "3");
            helper.assertLineQty($subline1, "1");
            helper.assertLineQty($subline2, "1");
            helper.assertLineQty($subline3, "1");
            helper.assert($subline1.find('.o_line_lot_name').text(), 'lot2');
            helper.assert($subline2.find('.o_line_lot_name').text(), 'lot1');
            helper.assert($subline3.find('.o_line_lot_name').text(), 'lot3');
        },
    },
    { trigger: '.o_barcode_client_action', run: 'scan O-BTN.validate' },
    { trigger: '.o_notification.border-success' },
]);

tour.register('test_batch_create', {test: true}, [
    {
        trigger: '.o_stock_barcode_main_menu:contains("Barcode Scanning")',
    },

    {
        trigger: '.button_batch_transfer',
    },

    {
        trigger: '.o-kanban-button-new',
    },

    {
        trigger: '.o_barcode_client_action',
        run: function () {
           const $pickingTypes = $('.o_barcode_picking_type');
           helper.assert($pickingTypes.length, 2, "Should contain Delivery Orders and Receipts");
        },
    },
    // select picking type
    {
        trigger: '.o_barcode_line_title:contains("Delivery Orders")'
    },

    {
        trigger: '.o_confirm:not([disabled])'
    },

    // select 2 delivery orders
    {
        trigger: '.o_barcode_line_title:contains("picking_delivery_1")',
    },

    {
        extra_trigger: '.o_highlight .o_barcode_line_title:contains("picking_delivery_1")',
        trigger: '.o_barcode_line_title:contains("picking_delivery_2")',
    },

    {
        extra_trigger: '.o_highlight .o_barcode_line_title:contains("picking_delivery_2")',
        trigger: '.o_confirm'
    },

    // from here should be the same as test_barcode_batch_delivery_1 => just check that it initially looks the same
    {
        trigger: '.o_picking_label',
        run: function () {
            currentViewState = updateState(defaultViewState, {
                linesCount: 7,
                scanMessage: 'scan_src',
            });
            checkState(currentViewState);
            const lines = document.querySelectorAll('.o_barcode_line')

            // Products comming from Section 1.
            helper.assertLineLocations(lines[0], '.../Section 1');
            helper.assertLineProduct(lines[0], 'product1');

            helper.assertLineLocations(lines[1], '.../Section 1');
            helper.assertLineProduct(lines[1], 'product1');

            helper.assertLineLocations(lines[2], '.../Section 1');
            helper.assertLineProduct(lines[2], 'product4');

            // Products coming from Section 2.
            helper.assertLineLocations(lines[3], '.../Section 2');
            helper.assertLineProduct(lines[3], 'product2');

            // Products coming from Section 3.
            helper.assertLineLocations(lines[4], '.../Section 3');
            helper.assertLineProduct(lines[4], 'product2');

            helper.assertLineLocations(lines[5], '.../Section 3');
            helper.assertLineProduct(lines[5], 'product3');

            // Products coming from Section 4.
            helper.assertLineLocations(lines[6], '.../Section 4');
            helper.assertLineProduct(lines[6], 'product4');

            // Checks each line belong to the right picking.
            helper.assertLinesBelongTo($([lines[0], lines[3], lines[4]]), 'picking_delivery_1');
            helper.assertLinesBelongTo($([lines[1], lines[2], lines[5], lines[6]]), 'picking_delivery_2');
        },
    },
]);

tour.register('test_put_in_pack_scan_suggested_package', {test: true}, [
    {
        trigger: '.o_barcode_client_action',
        run: function () {
            currentViewState = updateState(defaultViewState, {
                linesCount: 5,
                scanMessage: 'scan_src',
            });
            checkState(currentViewState);
            const lines = document.querySelectorAll('.o_barcode_line')

            // Products comming from Section 1.
            helper.assertLineLocations(lines[0], '.../Section 1');
            helper.assertLineProduct(lines[0], 'product1');

            helper.assertLineLocations(lines[1], '.../Section 1');
            helper.assertLineProduct(lines[1], 'product1');

            helper.assertLineLocations(lines[2], '.../Section 1');
            helper.assertLineProduct(lines[2], 'product3');

            // Products coming from Section 2.
            helper.assertLineLocations(lines[3], '.../Section 2');
            helper.assertLineProduct(lines[3], 'product2');

            helper.assertLineLocations(lines[4], '.../Section 2');
            helper.assertLineProduct(lines[4], 'product2');

            // Checks each line belong to the right picking.
            helper.assertLinesBelongTo($([lines[0], lines[2], lines[3]]), 'test_delivery_1');
            helper.assertLinesBelongTo($([lines[1], lines[4]]), 'test_delivery_2');
        },
    },

    // Scans the source (Section 1), the delivery 1 line's product and put it in pack.
    {
        trigger: '.o_barcode_client_action',
        run: 'scan LOC-01-01-00',
    },
    {
        trigger: '.o_scan_message.o_scan_product',
        run: 'scan product1',
    },
    {
        trigger: '.o_barcode_line:first-child.o_selected.o_line_completed',
        run: 'scan O-BTN.pack',
    },
    {
        trigger: '.o_barcode_line:contains("test_delivery_1"):contains("PACK")',
        run: function() {
            const [, line2, line3, , line4] = document.querySelectorAll('.o_barcode_line')
            helper.assert(line2.querySelector('[name=package]').innerText, 'PACK0000001 ?'); // Display suggested package.
            helper.assert(line3.querySelector('[name=package]').innerText, 'PACK0000001 ?'); // Display suggested package.
            helper.assert(line4.querySelector('[name=package]').innerText, 'PACK0000001');
        }
    },
    // Selects product3's line then scans PACK0000001 and product3.
    { trigger: '.o_barcode_line[data-barcode="product3"]' },
    { trigger: '.o_selected[data-barcode="product3"]', run: 'scan PACK0000001' },
    { trigger: '.o_barcode_client_action', run: 'scan product3' },
    {
        trigger: '.o_line_completed[data-barcode="product3"]',
        run: function() {
            const [, line2, line3, , line5] = document.querySelectorAll('.o_barcode_line')
            helper.assert(line2.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line3.querySelector('[name=package]').innerText, 'PACK0000001 ?'); // Display suggested package.
            helper.assert(line5.querySelector('[name=package]').innerText, 'PACK0000001');
        }
    },

    // Scans the delivery 2 line's product and put it in pack.
    {
        trigger: '.o_barcode_client_action',
        run: 'scan product1',
    },
    {
        trigger: '.o_barcode_line.o_selected.o_line_completed',
        run: 'scan O-BTN.pack',
    },
    {
        trigger: '.o_barcode_line:contains("test_delivery_2"):contains("PACK")',
        run: function() {
            const [line1, line2, line3, line4, line5] = document.querySelectorAll('.o_barcode_line')
            helper.assert(line1.querySelector('[name=package]').innerText, 'PACK0000001 ?'); // Display suggested package.
            helper.assert(line2.querySelector('[name=package]').innerText, 'PACK0000002 ?'); // Display suggested package.
            helper.assert(line3.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line4.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line5.querySelector('[name=package]').innerText, 'PACK0000002');
        }
    },

    // Scans the nex source location (Section 2).
    {
        trigger: '.o_barcode_client_action',
        run: 'scan LOC-01-02-00',
    },
    // Scans the delivery 1 line's product and put it in pack.
    {
        trigger: '.o_line_source_location:contains("Section 2") .fw-bold',
        run: 'scan product2',
    },
    {
        trigger: '.o_barcode_line.o_selected.o_line_completed',
        run: 'scan PACK0000001',
    },
    {
        trigger: '.o_barcode_line.o_selected:contains("PACK0000001"):not(:contains("?"))',
        run: function() {
            const [line1, line2, line3, line4, line5] = document.querySelectorAll('.o_barcode_line')
            helper.assert(line1.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line2.querySelector('[name=package]').innerText, 'PACK0000002 ?'); // Display suggested package.
            helper.assert(line3.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line4.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line5.querySelector('[name=package]').innerText, 'PACK0000002');
        }
    },

    // Scans the delivery 2 line's product and put it in pack.
    {
        trigger: '.o_barcode_client_action',
        run: 'scan product2',
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan PACK0000002',
    },
    {
        trigger: '.o_scan_message.o_scan_validate',
        run: function() {
            const [line1, line2, line3, line4, line5] = document.querySelectorAll('.o_barcode_line')
            helper.assert(line1.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line2.querySelector('[name=package]').innerText, 'PACK0000002');
            helper.assert(line3.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line4.querySelector('[name=package]').innerText, 'PACK0000001');
            helper.assert(line5.querySelector('[name=package]').innerText, 'PACK0000002');
        }
    },
    ...tour.stepUtils.validateBarcodeForm(),
]);

tour.register('test_pack_and_same_product_several_sml', {test: true}, [
    {
        trigger: '.o_barcode_client_action',
        run: 'scan P00001',
    },
    {
        trigger: '.qty-done:contains("3")',
        run: function() {
            const $lines =  helper.getLines({barcode: 'product1'});
            helper.assert($lines.length, 2);
            helper.assertLineIsHighlightedGreen($lines, true);
            helper.assertLineQty($($lines[0]), '3');
            helper.assertLineQty($($lines[1]), '7');
        },
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan P00001',
    },
    {
        trigger: '.o_notification.border-danger',
        run: function () {
            helper.assertErrorMessage('This package is already scanned.');
        },
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan P00002',
    },
    {
        trigger: '.qty-done:contains("25")',
        run: function() {
            const $lines =  helper.getLines({barcode: 'product2'});
            helper.assert($lines.length, 3);
            helper.assertLineIsHighlightedGreen($lines, true);
            helper.assertLineQty($($lines[0]), '25');
            helper.assertLineQty($($lines[1]), '30');
            helper.assertLineQty($($lines[2]), '45');
        },
    },
    {
        trigger: '.o_barcode_client_action',
        run: 'scan O-BTN.validate',
    },
    {
        trigger: '.o_notification.border-success',
    },
]);

tour.register("test_delete_from_batch", { test: true }, [
    {
        trigger: ".o_stock_barcode_main_menu:contains('Barcode Scanning')",
    },
    {
        trigger: ".button_batch_transfer",
    },
    {
        trigger: ".o-kanban-button-new",
    },
    {
        trigger: ".o_barcode_line_title:contains('Delivery Orders')",
    },
    {
        trigger: ".o_confirm:not([disabled])",
    },
    {
        trigger: ".o_barcode_line_title:contains('picking_delivery_1')",
    },
    {
        extra_trigger: ".o_highlight .o_barcode_line_title:contains('picking_delivery_1')",
        trigger: ".o_confirm",
    },
    {
        trigger: ".o_add_line",
    },
    {
        trigger: ".o_field_widget[name=product_id] input",
        run: "text productlot1",
    },
    {
        trigger: ".ui-menu-item > a:contains('productlot1')",
    },
    {
        trigger: ".o_save",
    },
    {
        trigger: ".o_barcode_line.o_selected .o_edit",
    },
    {
        trigger: ".o_delete",
    },
    {
        trigger: ".o_barcode_lines",
    },
]);

});
