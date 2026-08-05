<?php
/**
 * Plugin Name: CF7 RankBuilder CRM Webhook
 * Description: Sends Contact Form 7 submissions to RankBuilder CRM (WEBSITE source) alongside existing Twenty CRM hook
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) exit;

// RankBuilder CRM public endpoint + API key
define('RB_CRM_URL', 'https://dashboard.fortressblinds.co.za/api/leads/public');
define('RB_CRM_API_KEY', getenv('RB_CRM_API_KEY') ?: '');

function rb_crm_normalise_phone($phone) {
    $digits = preg_replace('/[^0-9+]/', '', $phone ?: '');
    if (!$digits) return '';
    if (strpos($digits, '+') === 0) return $digits;
    if (strpos($digits, '0') === 0 && strlen($digits) > 9) return '+27'.substr($digits, 1);
    return '+'.$digits;
}

function rb_crm_send_lead($posted_data, $form_id) {
    $email = sanitize_email($posted_data['email-address'] ?? $posted_data['your-email'] ?? '');
    if (!$email) return;

    $name    = sanitize_text_field($posted_data['first-name'] ?? $posted_data['your-name'] ?? '');
    $phone   = sanitize_text_field($posted_data['phone-number'] ?? '');
    $product = sanitize_text_field($posted_data['product-interest'] ?? $posted_data['your-subject'] ?? '');
    $message = sanitize_textarea_field($posted_data['your-message'] ?? $posted_data['message'] ?? '');

    // Split name into first/last
    $name_parts = preg_split('/\s+/', $name, 2);
    $first_name = $name_parts[0] ?: '';
    $last_name  = $name_parts[1] ?? '';

    $payload = [
        'source'           => 'WEBSITE',
        'contact_name'    => trim("$first_name $last_name"),
        'contact_email'   => $email,
        'contact_phone'    => rb_crm_normalise_phone($phone),
        'product_interest' => $product ?: 'General Enquiry',
        'message'          => $message,
        'location'         => 'FortressBlinds.co.za',
    ];

    $args = [
        'method'      => 'POST',
        'headers'     => [
            'Content-Type' => 'application/json',
            'X-API-Key'   => RB_CRM_API_KEY,
        ],
        'body'        => json_encode($payload),
        'timeout'     => 15,
        'redirection' => 5,
        'httpversion' => '1.1',
        'cookies'     => [],
    ];

    $response = wp_remote_post(RB_CRM_URL, $args);

    if (is_wp_error($response)) {
        error_log('[RankBuilder CRM] WP Error: ' . $response->get_error_message());
    } else {
        $code = wp_remote_retrieve_response_code($response);
        $body = wp_remote_retrieve_body($response);
        error_log(sprintf('[RankBuilder CRM] Sent lead | HTTP %d | %s', $code, substr($body, 0, 120)));
    }
}

// Hook into ALL CF7 forms — add priority 20 so it fires after Twenty CRM hook (priority 10)
add_action('wpcf7_before_send_mail', function ($contact_form) {
    $submission = WPCF7_Submission::get_instance();
    if (!$submission) return;

    $posted_data = $submission->get_posted_data();
    rb_crm_send_lead($posted_data, $contact_form->id());
}, 20);
