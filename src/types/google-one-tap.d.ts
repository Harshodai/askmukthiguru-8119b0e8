// Google One Tap / Identity Services types
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: GoogleOneTapConfig) => void;
          prompt: (callback?: (notification: GoogleOneTapNotification) => void) => void;
          renderButton: (parent: HTMLElement, options: GoogleOneTapButtonOptions) => void;
          disableAutoSelect: () => void;
          storeCredential: (credential: { id: string; password: string }) => void;
          cancel: () => void;
          revoke: (hint: string, callback: (response: GoogleRevokeResponse) => void) => void;
        };
      };
    };
  }
}

interface GoogleOneTapConfig {
  client_id: string;
  callback: (response: GoogleOneTapResponse) => void;
  auto_select?: boolean;
  cancel_on_tap_outside?: boolean;
  context?: 'signin' | 'signup' | 'use';
  itp_support?: boolean;
  nonce?: string;
  data_fedcm?: boolean;
  allowed_parent_origin?: string | string[];
  native_callback?: (response: GoogleOneTapResponse) => void;
  ux_mode?: 'popup' | 'redirect';
  redirect_uri?: string;
  state?: string;
  login_uri?: string;
  prompt_parent_id?: string;
  intermediate_iframe_close_callback?: () => void;
}

interface GoogleOneTapResponse {
  credential: string;
  select_by:
    | 'auto'
    | 'user'
    | 'user_1tap'
    | 'user_2tap'
    | 'btn'
    | 'btn_confirm'
    | 'brn_add_session'
    | 'btn_confirm_add_session';
  clientId?: string;
}

interface GoogleOneTapNotification {
  isDisplayed: () => boolean;
  isNotDisplayed: () => boolean;
  getNotDisplayedReason: () =>
    | 'browser_not_supported'
    | 'invalid_client'
    | 'missing_client_id'
    | 'opt_out_or_no_session'
    | 'secure_http_required'
    | 'suppressed_by_user'
    | 'unregistered_origin'
    | 'unknown_reason';
  isSkippedMoment: () => boolean;
  getSkippedReason: () =>
    | 'auto_cancel'
    | 'user_cancel'
    | 'tap_outside'
    | 'issuing_failed';
  isDismissedMoment: () => boolean;
  getDismissedReason: () => 'credential_returned' | 'cancel_called' | 'flow_restarted';
  getMomentType: () => 'display' | 'skipped' | 'dismissed';
}

interface GoogleOneTapButtonOptions {
  type?: 'standard' | 'icon';
  theme?: 'outline' | 'filled_blue' | 'filled_black';
  size?: 'large' | 'medium' | 'small';
  text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin';
  shape?: 'rectangular' | 'pill' | 'circle' | 'square';
  logo_alignment?: 'left' | 'center';
  width?: number;
  locale?: string;
}

interface GoogleRevokeResponse {
  successful: boolean;
  error?: string;
}

export {};
