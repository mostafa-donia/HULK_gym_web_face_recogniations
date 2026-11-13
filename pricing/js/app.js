/**
 * SYSTEMIZE — Presentation Style Pricing & Estimator
 * Direct, Fast & Interactive
 */

document.addEventListener('DOMContentLoaded', () => {
  initConfigEstimator();
  initScrollPill();
});

function initConfigEstimator() {
  const checkboxes = document.querySelectorAll('.calc-check');
  const liveTotalEl = document.getElementById('live-total-price');
  const pillTotalEl = document.getElementById('pill-total-display');
  const btnWhatsapp = document.getElementById('btn-whatsapp-quote');

  if (!checkboxes.length || !liveTotalEl) return;

  function formatNumber(num) {
    return new Intl.NumberFormat('en-US').format(num);
  }

  function calculate() {
    let total = 0;
    const selectedItems = [];

    checkboxes.forEach(cb => {
      const parentItem = cb.closest('.config-item');
      if (cb.checked) {
        const price = parseInt(cb.value, 10) || 0;
        const name = cb.getAttribute('data-name') || '';
        total += price;
        selectedItems.push({ name, price });
        if (parentItem) parentItem.classList.add('selected');
      } else {
        if (parentItem) parentItem.classList.remove('selected');
      }
    });

    const formatted = formatNumber(total);
    liveTotalEl.textContent = formatted;
    if (pillTotalEl) pillTotalEl.textContent = formatted;

    return { total, selectedItems };
  }

  // Event listener for checkboxes
  checkboxes.forEach(cb => {
    cb.addEventListener('change', calculate);
  });

  // Calculate initially
  calculate();

  // Generate WhatsApp Message on Click
  if (btnWhatsapp) {
    btnWhatsapp.addEventListener('click', () => {
      const { total, selectedItems } = calculate();

      let msg = `*طلب تجهيز وتشغيل نظام SYSTEMIZE لإدارة الجيم*\n\n`;
      msg += `لقد قمت باختيار التجهيزات التالية للجيم:\n`;

      if (selectedItems.length > 0) {
        selectedItems.forEach((item, idx) => {
          msg += `${idx + 1}. ${item.name} — ${formatNumber(item.price)} ج.م\n`;
        });
        msg += `\n*إجمالي التجهيز التقديري: ${formatNumber(total)} جنيه مصري.*\n\n`;
      } else {
        msg += `• البرنامج الأساسي لإدارة الجيم والاشتراكات.\n\n`;
      }

      msg += `يرجى التواصل معي لتحديد موعد المعاينة وبدء التشغيل والتنصيب.`;

      const encoded = encodeURIComponent(msg);
      window.open(`https://wa.me/201000000000?text=${encoded}`, '_blank');
    });
  }
}

function initScrollPill() {
  const pill = document.getElementById('floating-pill');
  if (!pill) return;

  window.addEventListener('scroll', () => {
    if (window.scrollY > 400) {
      pill.classList.add('visible');
    } else {
      pill.classList.remove('visible');
    }
  });
}
