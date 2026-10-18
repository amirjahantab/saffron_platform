/**
 * Modular Storefront JavaScript (Phase 6 - Sub-phases 6.1 & 6.2)
 * Handles:
 * 1. Interactive Variant Selection (Weight & Packaging) on Product Detail page.
 * 2. Dynamic updating of Price (Toman), Stock status, SKU, Harvest Batch, and Lab Metrics table.
 * 3. Quantity stepper (+ / -) respecting variant `min_order_quantity` and `max_order_quantity`.
 * 4. Progressive AJAX Add-to-Cart with live navbar badge updates and toast notifications.
 * 5. OTP Resend Countdown Timer on `/auth/login/`.
 * 6. Saved Address vs. New Address form toggle on `/checkout/`.
 */

(function () {
  "use strict";

  const PERSIAN_DIGITS = ["۰", "۱", "۲", "۳", "۴", "۵", "۶", "۷", "۸", "۹"];

  function toPersianDigits(val) {
    return String(val).replace(/\d/g, (d) => PERSIAN_DIGITS[Number(d)]);
  }

  function getCsrfToken() {
    const tokenInput = document.querySelector("input[name='csrfmiddlewaretoken']");
    if (tokenInput && tokenInput.value) {
      return tokenInput.value;
    }
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function showToast(message, isError = false) {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.className = [
      "flex items-center justify-between gap-3 px-4 py-3 rounded-xl shadow-lg border text-sm font-medium transition-all duration-300",
      isError
        ? "bg-rose-50 border-rose-300 text-rose-900"
        : "bg-emerald-50 border-emerald-300 text-emerald-900",
    ].join(" ");

    const textSpan = document.createElement("span");
    textSpan.textContent = message;

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "text-xs opacity-70 hover:opacity-100 px-1";
    closeBtn.setAttribute("aria-label", "بستن پیام");
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", () => toast.remove());

    toast.appendChild(textSpan);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    setTimeout(() => {
      if (toast.parentNode) {
        toast.remove();
      }
    }, 4500);
  }

  /**
   * 1. Interactive Variant Selector on Product Detail Page
   */
  function initProductDetailVariantSelector() {
    const dataScript = document.getElementById("product-variants-data");
    if (!dataScript) return;

    let variants = [];
    try {
      variants = JSON.parse(dataScript.textContent || "[]");
    } catch (e) {
      console.error("Failed to parse product variants JSON:", e);
      return;
    }
    if (!variants.length) return;

    const variantButtons = document.querySelectorAll(".variant-option-btn");
    const variantInput = document.getElementById("selected-variant-input");
    const qtyInput = document.getElementById("quantity-input");
    const qtyDecBtn = document.getElementById("qty-decrease-btn");
    const qtyIncBtn = document.getElementById("qty-increase-btn");
    const addToCartBtn = document.getElementById("add-to-cart-submit-btn");

    const skuEl = document.getElementById("variant-sku");
    const effectivePriceEl = document.getElementById("variant-effective-price");
    const basePriceContainer = document.getElementById("variant-base-price-container");
    const basePriceEl = document.getElementById("variant-base-price");
    const discountBadgeEl = document.getElementById("variant-discount-badge");
    const stockBadgeEl = document.getElementById("variant-stock-badge");
    const packagingNameEl = document.getElementById("variant-packaging-name");
    const netWeightEl = document.getElementById("variant-net-weight");
    const grossWeightEl = document.getElementById("variant-gross-weight");
    const saleTypeEl = document.getElementById("variant-sale-type");
    const batchCodeEl = document.getElementById("batch-code-val");
    const batchOriginEl = document.getElementById("batch-origin-val");
    const batchYearEl = document.getElementById("batch-year-val");
    const batchDryingEl = document.getElementById("batch-drying-val");
    const labCertContainer = document.getElementById("lab-certificates-container");

    function renderLabCertificates(certificates) {
      if (!labCertContainer) return;
      labCertContainer.replaceChildren();

      if (!certificates || !certificates.length) {
        const emptyP = document.createElement("p");
        emptyP.className = "text-sm text-stone-500 py-4";
        emptyP.textContent = "گواهی آزمایشگاهی عمومی برای این بچ ثبت نشده است.";
        labCertContainer.appendChild(emptyP);
        return;
      }

      certificates.forEach((cert) => {
        const card = document.createElement("div");
        card.className = "border border-stone-200 rounded-xl p-4 bg-white mb-4";

        const header = document.createElement("div");
        header.className = "flex flex-wrap items-center justify-between gap-3 pb-3 mb-3 border-b border-stone-100";

        const titleBox = document.createElement("div");
        const titleH4 = document.createElement("h4");
        titleH4.className = "font-bold text-stone-800 text-sm";
        titleH4.textContent = `${cert.lab_name} — شماره گواهی: ${cert.certificate_number}`;

        const metaP = document.createElement("p");
        metaP.className = "text-xs text-stone-500 mt-1";
        metaP.textContent = `استاندارد مرجع: ${cert.standard_reference} | نتیجه کیفی: ${cert.quality_grade_result} | تاریخ صدور: ${cert.issue_date}`;

        titleBox.appendChild(titleH4);
        titleBox.appendChild(metaP);
        header.appendChild(titleBox);

        if (cert.document_url) {
          const dlLink = document.createElement("a");
          dlLink.href = cert.document_url;
          dlLink.target = "_blank";
          dlLink.rel = "noopener noreferrer";
          dlLink.className = "inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-50 text-amber-900 border border-amber-200 hover:bg-amber-100";
          dlLink.textContent = "مشاهده و دانلود برگه اصالت آزمایشگاه";
          header.appendChild(dlLink);
        }

        card.appendChild(header);

        if (cert.metrics && cert.metrics.length) {
          const tableWrap = document.createElement("div");
          tableWrap.className = "overflow-x-auto";
          const table = document.createElement("table");
          table.className = "w-full text-right text-xs border-collapse";

          const thead = document.createElement("thead");
          thead.className = "bg-stone-50 text-stone-600 border-b border-stone-200";
          const headRow = document.createElement("tr");
          ["شاخص آزمایشگاهی", "مقدار اندازه‌گیری‌شده", "واحد", "حداقل استاندارد", "مرجع آزمون"].forEach((hText) => {
            const th = document.createElement("th");
            th.className = "py-2 px-3 font-semibold";
            th.textContent = hText;
            headRow.appendChild(th);
          });
          thead.appendChild(headRow);
          table.appendChild(thead);

          const tbody = document.createElement("tbody");
          cert.metrics.forEach((m) => {
            const tr = document.createElement("tr");
            tr.className = "border-b border-stone-100";

            const tdTitle = document.createElement("td");
            tdTitle.className = "py-2 px-3 font-medium text-stone-800";
            tdTitle.textContent = m.title;

            const tdVal = document.createElement("td");
            tdVal.className = "py-2 px-3 font-bold text-rose-800";
            tdVal.textContent = m.value;

            const tdUnit = document.createElement("td");
            tdUnit.className = "py-2 px-3 text-stone-600";
            tdUnit.textContent = m.unit;

            const tdMin = document.createElement("td");
            tdMin.className = "py-2 px-3 text-stone-600";
            tdMin.textContent = m.min_standard_limit;

            const tdRef = document.createElement("td");
            tdRef.className = "py-2 px-3 text-stone-500";
            tdRef.textContent = m.reference_method;

            tr.append(tdTitle, tdVal, tdUnit, tdMin, tdRef);
            tbody.appendChild(tr);
          });
          table.appendChild(tbody);
          tableWrap.appendChild(table);
          card.appendChild(tableWrap);
        }

        labCertContainer.appendChild(card);
      });
    }

    function applyVariantSelection(variantId) {
      const selected = variants.find((v) => v.public_id === variantId);
      if (!selected) return;

      variantButtons.forEach((btn) => {
        const isCurrent = btn.getAttribute("data-variant-id") === variantId;
        btn.setAttribute("aria-pressed", isCurrent ? "true" : "false");
      });

      if (variantInput) variantInput.value = selected.public_id;
      if (skuEl) skuEl.textContent = selected.sku;
      if (effectivePriceEl) effectivePriceEl.textContent = selected.formatted_effective_price_toman;

      if (basePriceContainer && basePriceEl && discountBadgeEl) {
        if (selected.has_discount) {
          basePriceContainer.classList.remove("hidden");
          basePriceEl.textContent = selected.formatted_base_price_toman;
          discountBadgeEl.textContent = `${selected.discount_percentage}٪ تخفیف`;
        } else {
          basePriceContainer.classList.add("hidden");
        }
      }

      if (packagingNameEl) packagingNameEl.textContent = selected.packaging_name;
      if (netWeightEl) netWeightEl.textContent = `${selected.net_weight_grams} گرم`;
      if (grossWeightEl) grossWeightEl.textContent = `${selected.gross_weight_grams} گرم`;
      if (saleTypeEl) saleTypeEl.textContent = selected.sale_type_label;

      if (selected.batch) {
        if (batchCodeEl) batchCodeEl.textContent = selected.batch.batch_code;
        if (batchOriginEl) batchOriginEl.textContent = selected.batch.origin_region;
        if (batchYearEl) batchYearEl.textContent = selected.batch.harvest_year;
        if (batchDryingEl) batchDryingEl.textContent = selected.batch.drying_method;
        renderLabCertificates(selected.batch.certificates);
      }

      if (qtyInput && addToCartBtn && stockBadgeEl) {
        if (selected.is_in_stock) {
          qtyInput.min = String(selected.min_order_quantity);
          qtyInput.max = String(selected.max_order_quantity);
          const currentVal = parseInt(qtyInput.value || "1", 10);
          const clamped = Math.max(
            selected.min_order_quantity,
            Math.min(currentVal, selected.max_order_quantity)
          );
          qtyInput.value = String(clamped);
          qtyInput.disabled = false;
          addToCartBtn.disabled = false;
          addToCartBtn.textContent = "افزودن به سبد خرید";
          stockBadgeEl.className = "inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200";
          stockBadgeEl.textContent = `موجود در انبار (${selected.stock_quantity_persian} عدد)`;
        } else {
          qtyInput.disabled = true;
          addToCartBtn.disabled = true;
          addToCartBtn.textContent = "ناموجود";
          stockBadgeEl.className = "inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-stone-100 text-stone-600 border border-stone-300";
          stockBadgeEl.textContent = "ناموجود در انبار";
        }
      }
    }

    variantButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const vid = btn.getAttribute("data-variant-id");
        if (vid) applyVariantSelection(vid);
      });
    });

    if (qtyDecBtn && qtyInput) {
      qtyDecBtn.addEventListener("click", () => {
        const min = parseInt(qtyInput.min || "1", 10);
        const current = parseInt(qtyInput.value || "1", 10);
        if (current > min) {
          qtyInput.value = String(current - 1);
        }
      });
    }

    if (qtyIncBtn && qtyInput) {
      qtyIncBtn.addEventListener("click", () => {
        const max = parseInt(qtyInput.max || "50", 10);
        const current = parseInt(qtyInput.value || "1", 10);
        if (current < max) {
          qtyInput.value = String(current + 1);
        }
      });
    }
  }

  /**
   * 2. Progressive AJAX Add-to-Cart Enhancement
   */
  function initAjaxAddToCartForms() {
    const forms = document.querySelectorAll(".js-add-to-cart-form");
    forms.forEach((form) => {
      form.addEventListener("submit", async (event) => {
        const apiUrl = form.getAttribute("data-api-url");
        if (!apiUrl || typeof window.fetch !== "function") {
          return;
        }

        event.preventDefault();
        const variantInput = form.querySelector("input[name='variant_public_id']");
        const qtyInput = form.querySelector("input[name='quantity']");
        const submitBtn = form.querySelector("button[type='submit']");

        if (!variantInput || !variantInput.value) {
          showToast("لطفاً یک گونه محصول را انتخاب کنید.", true);
          return;
        }

        const quantity = qtyInput ? parseInt(qtyInput.value || "1", 10) : 1;
        const originalText = submitBtn ? submitBtn.textContent : "";

        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = "در حال افزودن...";
        }

        try {
          const response = await fetch(apiUrl, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": getCsrfToken(),
            },
            body: JSON.stringify({
              variant_public_id: variantInput.value,
              quantity: quantity,
            }),
          });

          const data = await response.json();
          if (!response.ok || data.status !== "ok") {
            const errMsg = data.message || "خطا در افزودن محصول به سبد خرید.";
            showToast(errMsg, true);
            return;
          }

          showToast(data.message || "محصول به سبد خرید اضافه شد.", false);

          if (data.cart) {
            const countBadge = document.getElementById("nav-cart-count");
            const payableEl = document.getElementById("nav-cart-payable");
            if (countBadge) {
              countBadge.textContent = toPersianDigits(data.cart.total_units_count || 0);
            }
            if (payableEl && data.cart.pricing) {
              payableEl.textContent = data.cart.pricing.formatted_payable_toman;
            }
          }
        } catch (err) {
          form.submit();
        } finally {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
          }
        }
      });
    });
  }

  /**
   * 3. OTP Resend Countdown Timer on `/auth/login/`
   */
  function initOtpCountdownTimer() {
    const timerEl = document.getElementById("otp-countdown-timer");
    const resendBtn = document.getElementById("otp-resend-btn");
    if (!timerEl) return;

    let remaining = parseInt(timerEl.getAttribute("data-seconds") || "0", 10);
    if (isNaN(remaining) || remaining <= 0) {
      if (resendBtn) resendBtn.disabled = false;
      return;
    }

    const interval = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(interval);
        timerEl.textContent = "۰۰:۰۰";
        if (resendBtn) {
          resendBtn.disabled = false;
          resendBtn.classList.remove("opacity-50", "cursor-not-allowed");
        }
      } else {
        const mins = String(Math.floor(remaining / 60)).padStart(2, "0");
        const secs = String(remaining % 60).padStart(2, "0");
        timerEl.textContent = toPersianDigits(`${mins}:${secs}`);
      }
    }, 1000);
  }

  /**
   * 4. Checkout Saved Address vs. New Address Toggle on `/checkout/`
   */
  function initCheckoutAddressToggle() {
    const addressRadios = document.querySelectorAll("input[name='shipping_address_public_id']");
    const newAddressBox = document.getElementById("new-address-fields-container");
    if (!addressRadios.length || !newAddressBox) return;

    function updateVisibility() {
      let selectedValue = "";
      addressRadios.forEach((radio) => {
        if (radio.checked) selectedValue = radio.value;
      });
      if (!selectedValue) {
        newAddressBox.classList.remove("hidden");
      } else {
        newAddressBox.classList.add("hidden");
      }
    }

    addressRadios.forEach((radio) => {
      radio.addEventListener("change", updateVisibility);
    });
    updateVisibility();
  }

  document.addEventListener("DOMContentLoaded", () => {
    initProductDetailVariantSelector();
    initAjaxAddToCartForms();
    initOtpCountdownTimer();
    initCheckoutAddressToggle();
  });
})();