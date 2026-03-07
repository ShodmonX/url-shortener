const copyButtons = document.querySelectorAll(".copy-button");

for (const button of copyButtons) {
  button.addEventListener("click", async () => {
    const code = button.parentElement?.querySelector("code");
    if (!code) {
      return;
    }

    try {
      await navigator.clipboard.writeText(code.textContent ?? "");
      button.classList.add("is-copied");
      const original = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.textContent = original ?? "Copy";
        button.classList.remove("is-copied");
      }, 1600);
    } catch {
      button.textContent = "Copy failed";
      window.setTimeout(() => {
        button.textContent = "Copy";
      }, 1600);
    }
  });
}

const sections = document.querySelectorAll("main section[id]");
const navLinks = document.querySelectorAll(".toc a");

const observer = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) {
        continue;
      }

      for (const link of navLinks) {
        link.classList.toggle("is-active", link.getAttribute("href") === `#${entry.target.id}`);
      }
    }
  },
  {
    rootMargin: "-35% 0px -45% 0px",
    threshold: 0,
  },
);

for (const section of sections) {
  observer.observe(section);
}
