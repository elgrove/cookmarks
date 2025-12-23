import logging
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from core.models import ExtractionReport

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Recalculate costs for extraction reports that used gemini-2.5-flash with updated pricing"
    )

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate cost based on token counts using gemini-2.5-flash pricing."""
        # Updated pricing for gemini-2.5-flash
        input_rate = 0.30  # $0.30 per million input tokens
        output_rate = 2.50  # $2.50 per million output tokens

        cost_usd = (input_tokens / 1_000_000) * input_rate + (
            output_tokens / 1_000_000
        ) * output_rate
        return Decimal(str(cost_usd))

    def handle(self, *args, **options):
        self.stdout.write("\nRecalculating costs for gemini-2.5-flash extraction reports")
        self.stdout.write("Pricing: $0.30/M input tokens, $2.50/M output tokens\n")

        # Find all extraction reports with gemini-2.5-flash and token data
        reports = ExtractionReport.objects.filter(
            Q(model_name="gemini-2.5-flash") | Q(model_name__icontains="2.5-flash"),
            input_tokens__isnull=False,
            output_tokens__isnull=False,
        ).select_related("book")

        total_reports = reports.count()

        if total_reports == 0:
            self.stdout.write(
                self.style.WARNING(
                    "\n✗ No extraction reports found with gemini-2.5-flash that have token data\n"
                )
            )
            return

        self.stdout.write(f"Found {total_reports} extraction reports to process\n")
        self.stdout.write("-" * 80)

        updated_count = 0
        total_old_cost = Decimal("0")
        total_new_cost = Decimal("0")

        for report in reports:
            old_cost = report.cost_usd or Decimal("0")
            new_cost = self.calculate_cost(report.input_tokens, report.output_tokens)

            cost_diff = new_cost - old_cost
            total_old_cost += old_cost
            total_new_cost += new_cost

            # Display report info
            self.stdout.write(f"\n📚 {report.book.title[:50]}")
            self.stdout.write(f"   ID: {report.id} | Completed: {report.completed_at}")
            self.stdout.write(
                f"   Tokens: {report.input_tokens:,} input, {report.output_tokens:,} output"
            )
            self.stdout.write(
                f"   Old cost: ${old_cost:.6f} → New cost: ${new_cost:.6f} "
                f"({'+' if cost_diff >= 0 else ''}{cost_diff:.6f})"
            )

            report.cost_usd = new_cost
            report.save(update_fields=["cost_usd"])
            updated_count += 1

        # Summary
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("\nSUMMARY")
        self.stdout.write("-" * 80)
        self.stdout.write(f"Reports processed: {total_reports}")
        self.stdout.write(f"Reports updated: {updated_count}")
        self.stdout.write(f"\nTotal old cost: ${total_old_cost:.6f}")
        self.stdout.write(f"Total new cost: ${total_new_cost:.6f}")

        cost_difference = total_new_cost - total_old_cost
        self.stdout.write(
            f"Difference: {'+' if cost_difference >= 0 else ''}${cost_difference:.6f}"
        )

        self.stdout.write(
            self.style.SUCCESS(f"\n✓ Successfully updated {updated_count} extraction reports\n")
        )
