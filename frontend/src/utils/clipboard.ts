function fallbackCopyToClipboard(text: string): boolean {
  if (typeof document.execCommand !== "function") {
    return false;
  }

  if (!document.body) {
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

  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();

  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    if (textarea.parentNode === document.body) {
      document.body.removeChild(textarea);
    }
    if (previousActiveElement?.isConnected) {
      previousActiveElement.focus();
    }
  }
}

export async function copyToClipboard(text: string): Promise<boolean> {
  const clipboardWriteAvailable =
    window.isSecureContext && typeof navigator.clipboard?.writeText === "function";

  if (clipboardWriteAvailable) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      if (fallbackCopyToClipboard(text)) {
        return true;
      }
    }
  }

  if (fallbackCopyToClipboard(text)) {
    return true;
  }

  return false;
}
