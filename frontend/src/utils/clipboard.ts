type CopyToClipboardOptions = {
  fallbackTarget?: HTMLElement | null;
};

function getFallbackContainer(fallbackTarget?: HTMLElement | null): HTMLElement | null {
  if (!document.body) {
    return null;
  }

  const target = fallbackTarget?.isConnected
    ? fallbackTarget
    : document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
  const dialog = target?.closest<HTMLElement>('[role="dialog"]');

  return dialog?.isConnected ? dialog : document.body;
}

function fallbackCopyToClipboard(text: string, fallbackTarget?: HTMLElement | null): boolean {
  if (typeof document.execCommand !== "function") {
    return false;
  }

  const container = getFallbackContainer(fallbackTarget);
  if (!container) {
    return false;
  }

  const previousActiveElement =
    document.activeElement instanceof HTMLElement ? document.activeElement : null;
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.setAttribute("aria-hidden", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "-9999px";
  textarea.style.opacity = "0";

  container.appendChild(textarea);
  textarea.focus();
  textarea.select();

  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    if (textarea.parentElement) {
      textarea.parentElement.removeChild(textarea);
    }
    if (previousActiveElement?.isConnected) {
      previousActiveElement.focus();
    }
  }
}

export async function copyToClipboard(
  text: string,
  options: CopyToClipboardOptions = {},
): Promise<boolean> {
  const clipboardWriteAvailable =
    window.isSecureContext && typeof navigator.clipboard?.writeText === "function";

  if (clipboardWriteAvailable) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      if (fallbackCopyToClipboard(text, options.fallbackTarget)) {
        return true;
      }
    }
  }

  if (fallbackCopyToClipboard(text, options.fallbackTarget)) {
    return true;
  }

  return false;
}
