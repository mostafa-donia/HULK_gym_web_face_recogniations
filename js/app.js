/**
 * SYSTEMIZE — Loss-Prevention Pitch & Dynamic Estimator
 * Direct, Shock Numbers & Zero Clutter
 */

document.addEventListener('DOMContentLoaded', () => {
  initLiveCalculator();
  initBottomOnlyPill();
});

function initLiveCalculator() {
  const toggles = document.querySelectorAll('.addon-toggle');
  const totalPriceEl = document.getElementById('total-price');
  const pillPriceEl = document.getElementById('pill-price-val');
  const btnSendWhatsapp = document.getElementById('btn-send-whatsapp');
  const pillWhatsappLink = document.getElementById('pill-whatsapp-link');

  if (!toggles.length || !totalPriceEl) return;

  function formatNumber(num) {
    return new Intl.NumberFormat('en-US').format(num);
  }

  function calculate() {
    let total = 0;
    const selectedItems = [];

    toggles.forEach(toggle => {
      const parentLabel = toggle.closest('.calc-box-item');
      if (toggle.checked) {
        const price = parseInt(toggle.value, 10) || 0;
        const name = toggle.getAttribute('data-name') || '';
        total += price;
        selectedItems.push({ name, price });
        if (parentLabel) parentLabel.classList.add('selected');
      } else {
        if (parentLabel) parentLabel.classList.remove('selected');
      }
    });

    const formatted = formatNumber(total);
    totalPriceEl.textContent = formatted;
    if (pillPriceEl) pillPriceEl.textContent = formatted;

    return { total, selectedItems };
  }

  toggles.forEach(t => t.addEventListener('change', calculate));

  // Run initial calculation
  calculate();

  // WhatsApp Message Generator
  function getWhatsAppUrl() {
    const { total, selectedItems } = calculate();

    let msg = `*طلب تجهيز وتشغيل نظام SYSTEMIZE لإدارة الجيم*\n\n`;
    msg += `أود تأمين وقفل ثغرات التسريب في الجيم مع التجهيزات التالية:\n`;

    if (selectedItems.length > 0) {
      selectedItems.forEach((item, idx) => {
        msg += `${idx + 1}. ${item.name} — ${formatNumber(item.price)} ج.م\n`;
      });
      msg += `\n*إجمالي التجهيز التقديري: ${formatNumber(total)} جنيه مصري.*\n\n`;
    } else {
      msg += `• النظام الأساسي لإدارة الجيم والاشتراكات.\n\n`;
    }

    msg += `يرجى التواصل معي لتنسيق موعد التنصيب وبدء التشغيل الفوري.`;
    return `https://wa.me/201000000000?text=${encodeURIComponent(msg)}`;
  }

  if (btnSendWhatsapp) {
    btnSendWhatsapp.addEventListener('click', () => {
      window.open(getWhatsAppUrl(), '_blank');
    });
  }

  if (pillWhatsappLink) {
    pillWhatsappLink.addEventListener('click', (e) => {
      e.preventDefault();
      window.open(getWhatsAppUrl(), '_blank');
    });
  }
}

/**
 * Show the floating pill ONLY when the user reaches the bottom of the page
 */
function initBottomOnlyPill() {
  const bottomPill = document.getElementById('bottom-pill');
  if (!bottomPill) return;

  function checkScrollPosition() {
    const scrollY = window.scrollY || window.pageYOffset;
    const viewportHeight = window.innerHeight;
    const fullHeight = document.documentElement.scrollHeight;

    // Show only when user has scrolled past 80% of the page or within 600px of the footer
    const distanceToBottom = fullHeight - (scrollY + viewportHeight);

    if (distanceToBottom < 650 || (scrollY + viewportHeight) / fullHeight > 0.82) {
      bottomPill.classList.add('is-visible');
    } else {
      bottomPill.classList.remove('is-visible');
    }
  }

  window.addEventListener('scroll', checkScrollPosition, { passive: true });
  window.addEventListener('resize', checkScrollPosition);
  checkScrollPosition();
}
