export async function copyWithFeedback(
  text: string,
  button: HTMLButtonElement,
  resetDelayMs = 1000,
): Promise<void> {
  await navigator.clipboard.writeText(text);

  const originalText = button.textContent;
  const originalColor = button.style.color;

  button.textContent = "✓";
  button.style.color = "#4ADE80";

  window.setTimeout(() => {
    button.textContent = originalText;
    button.style.color = originalColor;
  }, resetDelayMs);
}
